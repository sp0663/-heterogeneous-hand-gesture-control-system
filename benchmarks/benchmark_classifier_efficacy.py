"""
Feeds a standardised static dataset of spatial landmark coordinates into
BOTH classifier pipelines and computes:
  - Confusion matrix
  - Per-class Precision, Recall, F1-Score
  - Macro-averaged and weighted-averaged metrics
  - Overall accuracy

The four gesture classes evaluated (shared by both pipelines):
  fist | open_palm | index_finger | pinch

MODES
-----
  --mode software     : run software classifier only (no hardware needed)
  --mode hardware     : run FPGA classifier only (requires --port)
  --mode both         : run both and produce a side-by-side comparison

SOFTWARE CLASSIFIER
-------------------
  Uses GestureRecogniser from gesture_media_controller.
  A fresh instance is created per sample to avoid state carry-over.

FPGA CLASSIFIER
---------------
  Serialises each sample via build_frame_bytes() and sends over UART.
  Receives 1-byte ACK from the FPGA containing gesture_id[2:0].
  Falls back to SOFTWARE FPGA REPLICA if --port is omitted.

SOFTWARE FPGA REPLICA
---------------------
  A pure-Python reimplementation of gesture_classifier.v logic
  (dist-based pinch, angle-based finger extension, fist/open/index rules).
  Activated automatically when --port is not supplied in hardware/both mode.

Usage
-----
    python benchmark_classifier_efficacy.py --mode software
    python benchmark_classifier_efficacy.py --mode hardware --port /dev/ttyUSB1
    python benchmark_classifier_efficacy.py --mode both     --port /dev/ttyUSB1
    python benchmark_classifier_efficacy.py --mode both     # uses FPGA replica

UART FRAMING NOTE
-----------------
The first hardware run on this benchmark produced ~40% accuracy versus
~76% from the software replica running the identical Verilog logic. Root
cause: coord_assembler.v advances a 5-byte landmark counter without any
frame-sync byte. If a single byte is dropped or duplicated mid-stream
(USB scheduling jitter, FIFO race, or a stray byte left over from a
previous transmission) the counter never resyncs -- every subsequent
landmark is parsed at the wrong byte offset.

This script applies the strongest software-only mitigations available:
  * full input AND output buffer flush before every payload,
  * inter-sample settling delay so the FPGA reaches byte_counter==0
    before the next 105-byte burst arrives,
  * single retry on ACK timeout with an extended flush window,
  * per-sample retry/timeout counters surfaced in the JSON output.

A complete fix requires an RTL change: prepend a 0xAA sync byte to each
frame on the Jetson side, and have coord_assembler.v hold IDLE until it
sees one. The hooks below (PRE_FRAME_SYNC) are wired through so the
software side is ready to send the sync byte once the RTL is updated.
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import numpy as np

_REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_HOMO_DIR   = os.path.join(_REPO_ROOT, "homogeneous_system")
_HETERO_DIR = os.path.join(_REPO_ROOT, "heterogeneous_system", "app")
sys.path.insert(0, _HOMO_DIR)
sys.path.insert(0, _HETERO_DIR)

RESULTS_DIR  = os.path.join(os.path.dirname(__file__), "results")
DATASET_PATH = os.path.join(os.path.dirname(__file__), "data", "static_gesture_dataset.json")

FPGA_ID_TO_LABEL = {0:"pinch", 1:"fist", 2:"open_palm",
                    3:"index_finger", 4:"unknown", 5:"pinch_cw", 6:"pinch_acw"}
CLASSES = ["fist", "open_palm", "index_finger", "pinch"]

# Set to b"\xAA" once coord_assembler.v gains a sync-byte detector.
PRE_FRAME_SYNC = b""

# Software-side hardening parameters (override with CLI flags).
DEFAULT_INTER_SAMPLE_MS = 5.0
DEFAULT_ACK_TIMEOUT_S   = 0.75
DEFAULT_RETRY_FLUSH_MS  = 50.0


#  Software FPGA Replica
#  Mirrors gesture_classifier.v + feature_extractor.v logic in Python

def _sq_dist_norm(lm_norm, id1, id2):
    a = lm_norm[id1]
    b = lm_norm[id2]
    return (a["nx"] - b["nx"]) ** 2 + (a["ny"] - b["ny"]) ** 2


def _vec_angle_norm(lm_norm, id1, id2, id3):
    p1 = np.array([lm_norm[id1]["nx"], lm_norm[id1]["ny"]], dtype=float)
    p2 = np.array([lm_norm[id2]["nx"], lm_norm[id2]["ny"]], dtype=float)
    p3 = np.array([lm_norm[id3]["nx"], lm_norm[id3]["ny"]], dtype=float)
    v1 = p1 - p2
    v2 = p3 - p2
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))


def fpga_replica_classify(lm_norm: list) -> str:
    lm = {d["id"]: d for d in lm_norm}

    dist_ti  = _sq_dist_norm(lm, 4, 8)
    dist_wm  = _sq_dist_norm(lm, 0, 12)
    is_pinch = (dist_ti * 16) < dist_wm

    if is_pinch:
        return "pinch"

    thumb_ext   = _vec_angle_norm(lm, 2, 3, 4)   > 160
    index_ext   = _vec_angle_norm(lm, 5, 6, 7)   > 160
    middle_ext  = _vec_angle_norm(lm, 9, 10, 11) > 160
    ring_ext    = _vec_angle_norm(lm, 13, 14, 15) > 160
    pinky_ext   = _vec_angle_norm(lm, 17, 18, 19) > 160

    if not index_ext and not middle_ext and not ring_ext and not pinky_ext:
        return "fist"
    if thumb_ext and index_ext and middle_ext and ring_ext and pinky_ext:
        return "open_palm"
    if index_ext and not middle_ext and not ring_ext and not pinky_ext:
        return "index_finger"
    return "unknown"


#  Software classifier (GestureRecogniser)

def software_classify(sample: dict) -> tuple:
    from gesture_recogniser import GestureRecogniser
    recon = GestureRecogniser()
    lm    = sample["landmarks_px"]

    recon.recognise_gesture(lm, "Right", None)

    t0 = time.perf_counter()
    pred = recon.recognise_gesture(lm, "Right", None)
    t1 = time.perf_counter()
    latency = (t1 - t0) * 1e3

    label_map = {
        "fist":                "fist",
        "open_palm":           "open_palm",
        "index_pointing":      "index_finger",
        "pinch":               "pinch",
        "pinch_clockwise":     "pinch_cw",
        "pinch_anticlockwise": "pinch_acw",
        "unknown":             "unknown",
    }
    pred_norm = label_map.get(pred, pred)
    return pred_norm, latency


#  FPGA / replica classifier

def _send_payload(ser, payload):
    """Single write+ack attempt. Returns (ack_byte_or_None, elapsed_ms)."""
    if PRE_FRAME_SYNC:
        ser.write(PRE_FRAME_SYNC)
    t0 = time.perf_counter()
    ser.write(payload)
    ser.flush()
    ack = ser.read(1)
    t1 = time.perf_counter()
    return (ack if len(ack) == 1 else None), (t1 - t0) * 1e3


def fpga_classify_serial(sample, ser, settle_ms, retry_flush_ms, stats):
    """
    Send 105-byte UART frame, receive 1-byte ACK.
    Hardened against the no-frame-sync issue: full flush before every send,
    inter-sample settle so the FPGA's byte_counter wraps to 0 before the
    next burst, and one retry on ACK timeout.

    Returns (predicted_label, latency_ms).
    """
    payload = bytearray(sample["uart_frame_bytes"])

    # Full flush -- drop any straggler bytes from prior sample's ACK path
    # AND any half-written bytes still buffered in the OS TX queue.
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    ack, lat = _send_payload(ser, payload)

    if ack is None:
        # Suspected misalignment or dropped byte. Give the FPGA enough idle
        # time that any half-parsed landmark has been written (wrong slot,
        # but the byte_counter at least returns to 0 every 5 bytes), then
        # retry once with a longer flush window.
        stats["timeouts"] += 1
        time.sleep(retry_flush_ms / 1000.0)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ack, lat = _send_payload(ser, payload)
        if ack is not None:
            stats["retries_recovered"] += 1

    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

    if ack is None:
        return "timeout", lat
    gid = ack[0] & 0x07
    return FPGA_ID_TO_LABEL.get(gid, f"id={gid}"), lat


def fpga_classify_replica(sample: dict) -> tuple:
    t0   = time.perf_counter()
    pred = fpga_replica_classify(sample["landmarks_norm"])
    t1   = time.perf_counter()
    return pred, (t1 - t0) * 1e3


#  Metrics

def confusion_matrix(y_true: list, y_pred: list, classes: list) -> np.ndarray:
    n   = len(classes)
    idx = {c: i for i, c in enumerate(classes)}
    cm  = np.zeros((n, n), dtype=int)
    for t, p in zip(y_true, y_pred):
        ti = idx.get(t, -1)
        pi = idx.get(p, -1)
        if ti >= 0 and pi >= 0:
            cm[ti][pi] += 1
    return cm


def class_metrics(cm: np.ndarray, classes: list) -> dict:
    metrics = {}
    for i, cls in enumerate(classes):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)
        metrics[cls] = {
            "tp": int(tp), "fp": int(fp), "fn": int(fn),
            "precision": round(precision, 4),
            "recall":    round(recall,    4),
            "f1_score":  round(f1,        4),
        }
    total = cm.sum()
    accuracy = float(np.trace(cm)) / total if total > 0 else 0.0

    p_vals = [metrics[c]["precision"] for c in classes]
    r_vals = [metrics[c]["recall"]    for c in classes]
    f_vals = [metrics[c]["f1_score"]  for c in classes]

    support = {c: int(cm[i, :].sum()) for i, c in enumerate(classes)}
    wt_p = sum(metrics[c]["precision"] * support[c] for c in classes) / total
    wt_r = sum(metrics[c]["recall"]    * support[c] for c in classes) / total
    wt_f = sum(metrics[c]["f1_score"]  * support[c] for c in classes) / total

    return {
        "per_class":         metrics,
        "accuracy":          round(accuracy, 4),
        "macro_precision":   round(sum(p_vals) / len(p_vals), 4),
        "macro_recall":      round(sum(r_vals) / len(r_vals), 4),
        "macro_f1":          round(sum(f_vals) / len(f_vals), 4),
        "weighted_precision":round(wt_p, 4),
        "weighted_recall":   round(wt_r, 4),
        "weighted_f1":       round(wt_f, 4),
        "support":           support,
    }


def print_confusion_matrix(cm: np.ndarray, classes: list, title: str):
    w = 14
    print(f"\n  {title}")
    print("  " + "-" * (w * (len(classes) + 1) + 2))
    header = f"  {'True / Pred':<{w}}" + "".join(f"{c:>{w}}" for c in classes)
    print(header)
    print("  " + "-" * (w * (len(classes) + 1) + 2))
    for i, cls in enumerate(classes):
        row = f"  {cls:<{w}}" + "".join(f"{cm[i,j]:>{w}}" for j in range(len(classes)))
        print(row)
    print("  " + "-" * (w * (len(classes) + 1) + 2))


def print_metrics(m: dict, title: str):
    print(f"\n  {title}")
    print(f"  {'Class':<16} {'Precision':>10} {'Recall':>10} {'F1-Score':>10} {'Support':>10}")
    print("  " + "-" * 58)
    for cls, v in m["per_class"].items():
        print(f"  {cls:<16} {v['precision']:>10.4f} {v['recall']:>10.4f} "
              f"{v['f1_score']:>10.4f} {m['support'][cls]:>10}")
    print("  " + "-" * 58)
    print(f"  {'Macro avg':<16} {m['macro_precision']:>10.4f} "
          f"{m['macro_recall']:>10.4f} {m['macro_f1']:>10.4f}")
    print(f"  {'Weighted avg':<16} {m['weighted_precision']:>10.4f} "
          f"{m['weighted_recall']:>10.4f} {m['weighted_f1']:>10.4f}")
    print(f"\n  Overall Accuracy : {m['accuracy']:.4f}  "
          f"({m['accuracy']*100:.2f}%)")


#  Save

def save_results(results: dict, ts: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    base  = f"classifier_efficacy_{ts}"
    jpath = os.path.join(RESULTS_DIR, base + ".json")
    cpath = os.path.join(RESULTS_DIR, base + ".csv")

    with open(jpath, "w") as f:
        json.dump(results, f, indent=2)

    rows = results.get("per_sample", [])
    if rows:
        with open(cpath, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                               extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    print(f"\n  JSON → {jpath}")
    print(f"  CSV  → {cpath}")


#  Main

def run_pipeline(mode, dataset, port, baud, ack_timeout, settle_ms, retry_flush_ms):
    samples    = dataset["samples"]
    per_sample = []

    sw_true, sw_pred = [], []
    fp_true, fp_pred = [], []

    ser = None
    use_replica = True
    uart_stats = {"timeouts": 0, "retries_recovered": 0}

    if mode in ("hardware", "both") and port:
        import serial
        print(f"[efficacy] Opening {port} @ {baud} baud …")
        ser = serial.Serial(port, baud, timeout=ack_timeout)
        try:
            ser.set_low_latency_mode(True)
        except Exception:
            pass
        # Allow the FPGA UART RX FSM to finish initialising and the
        # USB-serial chip's auto-DTR pulse (~1.5 s on FT2232) to settle.
        time.sleep(2.5)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        use_replica = False
    elif mode in ("hardware", "both") and not port:
        print("[efficacy] No --port supplied → using software FPGA replica.")

    print(f"[efficacy] Classifying {len(samples)} samples …")

    for s in samples:
        row = {
            "sample_id":  s["sample_id"],
            "true_label": s["true_label"],
        }

        if mode in ("software", "both"):
            pred_sw, lat_sw = software_classify(s)
            sw_true.append(s["true_label"])
            sw_pred.append(pred_sw)
            row["sw_prediction"] = pred_sw
            row["sw_latency_ms"] = round(lat_sw, 4)
            row["sw_correct"]    = int(pred_sw == s["true_label"])

        if mode in ("hardware", "both"):
            if use_replica:
                pred_fp, lat_fp = fpga_classify_replica(s)
            else:
                pred_fp, lat_fp = fpga_classify_serial(
                    s, ser, settle_ms, retry_flush_ms, uart_stats
                )
            fp_true.append(s["true_label"])
            fp_pred.append(pred_fp)
            row["fpga_prediction"] = pred_fp
            row["fpga_latency_ms"] = round(lat_fp, 4)
            row["fpga_correct"]    = int(pred_fp == s["true_label"])

        per_sample.append(row)

    if ser:
        ser.close()

    results = {
        "metadata": {
            "dataset":       DATASET_PATH,
            "total_samples": len(samples),
            "mode":          mode,
            "fpga_backend":  "serial" if (not use_replica and mode != "software")
                             else "software_replica",
            "classes":       CLASSES,
            "uart_settle_ms":     settle_ms,
            "uart_ack_timeout_s": ack_timeout,
            "uart_retry_flush_ms": retry_flush_ms,
            "uart_stats":         uart_stats,
        },
        "per_sample": per_sample,
    }

    if sw_true:
        cm_sw = confusion_matrix(sw_true, sw_pred, CLASSES)
        m_sw  = class_metrics(cm_sw, CLASSES)
        sep   = "=" * 62
        print(f"\n{sep}")
        print("  SOFTWARE CLASSIFIER (GestureRecogniser) - Efficacy")
        print(sep)
        print_confusion_matrix(cm_sw, CLASSES, "Confusion Matrix")
        print_metrics(m_sw, "Classification Report")
        results["software_classifier"] = {
            "confusion_matrix": cm_sw.tolist(),
            "metrics":          m_sw,
            "mean_latency_ms":  round(
                sum(r["sw_latency_ms"] for r in per_sample
                    if "sw_latency_ms" in r) / len(sw_true), 4),
        }

    if fp_true:
        cm_fp = confusion_matrix(fp_true, fp_pred, CLASSES)
        m_fp  = class_metrics(cm_fp, CLASSES)
        label = ("FPGA Classifier (Hardware UART)"
                 if not use_replica else "FPGA Replica (Software)")
        sep   = "=" * 62
        print(f"\n{sep}")
        print(f"  {label} - Efficacy")
        print(sep)
        print_confusion_matrix(cm_fp, CLASSES, "Confusion Matrix")
        print_metrics(m_fp, "Classification Report")
        if not use_replica:
            print(f"\n  UART hardening stats: "
                  f"{uart_stats['timeouts']} timeouts, "
                  f"{uart_stats['retries_recovered']} recovered on retry.")
        results["fpga_classifier"] = {
            "backend":          "serial" if not use_replica else "software_replica",
            "confusion_matrix": cm_fp.tolist(),
            "metrics":          m_fp,
            "mean_latency_ms":  round(
                sum(r["fpga_latency_ms"] for r in per_sample
                    if "fpga_latency_ms" in r) / len(fp_true), 4),
        }

    return results


def main():
    ap = argparse.ArgumentParser(
        description="Classifier efficacy benchmark (confusion matrix, P/R/F1).")
    ap.add_argument("--mode",          choices=["software","hardware","both"],
                    default="both")
    ap.add_argument("--dataset",       default=DATASET_PATH,
                    help="Path to static_gesture_dataset.json")
    ap.add_argument("--port",          default=None,
                    help="Serial port for FPGA (e.g. /dev/ttyUSB1). "
                         "Omit to use software FPGA replica.")
    ap.add_argument("--baud",          type=int,   default=115200)
    ap.add_argument("--ack-timeout",   type=float, default=DEFAULT_ACK_TIMEOUT_S,
                    help="Per-sample ACK read timeout in seconds.")
    ap.add_argument("--settle-ms",     type=float, default=DEFAULT_INTER_SAMPLE_MS,
                    help="Idle gap between samples so the FPGA's "
                         "byte_counter wraps to 0 before the next burst.")
    ap.add_argument("--retry-flush-ms", type=float, default=DEFAULT_RETRY_FLUSH_MS,
                    help="Flush window before retrying a timed-out sample.")
    args = ap.parse_args()

    if not os.path.exists(args.dataset):
        sys.exit(f"[ERROR] Dataset not found: {args.dataset}\n"
                 f"  Run: python generate_static_dataset.py")

    with open(args.dataset) as f:
        dataset = json.load(f)

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = run_pipeline(
        args.mode, dataset, args.port, args.baud,
        args.ack_timeout, args.settle_ms, args.retry_flush_ms,
    )
    save_results(results, ts)


if __name__ == "__main__":
    main()
