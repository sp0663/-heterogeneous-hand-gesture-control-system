"""
Full-pipeline latency + throughput benchmark for the Jetson + FPGA
heterogeneous architecture.

Pipeline stages timed with time.perf_counter():
  1. Camera Capture
  2. MediaPipe Hand Detection
  3. Landmark Normalisation & Serialisation  (build_frame_bytes)
  4. UART TX  (ser.write + ser.flush)           ← UART overhead
  5. FPGA Pipeline + UART RX  (ser.read(1))     ← UART overhead
  6. Command Mapping Lookup

UART theoretical floor (105 TX + 1 RX bytes @ 115200 8N1):
  (106 bytes × 10 bits/byte) / 115200 bps × 1000 = 9.20 ms

FPGA pipeline latency (estimated):
  fpga_only ≈ (stage5_total) − UART_floor

Outputs
-------
  results/heterogeneous_latency_<timestamp>.json
  results/heterogeneous_latency_<timestamp>.csv

Usage
-----
    cd comparative_benchmarks/
    python benchmark_heterogeneous.py [--samples 500] [--port /dev/ttyUSB1]
                                      [--baud 115200] [--device 0] [--no-display]
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import cv2
import numpy as np
import serial

_REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_HETERO_DIR = os.path.join(_REPO_ROOT, "heterogeneous_system", "app")
sys.path.insert(0, _HETERO_DIR)

from hand_tracker import HandTracker
from config       import GESTURE_COMMANDS, VLC_KEYS

GESTURE_NAMES = {
    0: "pinch", 1: "fist", 2: "open_palm",
    3: "index_finger", 4: "unknown",
    5: "pinch_clockwise", 6: "pinch_anticlockwise",
}

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _uart_floor_ms(baud: int) -> float:
    """Theoretical minimum transfer time: 105 TX + 1 RX bytes, 8N1."""
    return (106 * 10 / baud) * 1e3


def _stats(arr: np.ndarray) -> dict:
    return {
        "mean":   float(np.mean(arr)),
        "std":    float(np.std(arr)),
        "min":    float(np.min(arr)),
        "max":    float(np.max(arr)),
        "median": float(np.median(arr)),
        "p95":    float(np.percentile(arr, 95)),
        "p99":    float(np.percentile(arr, 99)),
    }


def _jitter(arr: np.ndarray) -> dict:
    d = np.diff(arr)
    return {
        "mean_abs_ms": float(np.mean(np.abs(d))),
        "std_ms":      float(np.std(d)),
        "max_abs_ms":  float(np.max(np.abs(d))),
    }


def build_frame_bytes(landmarks: list) -> bytearray:
    """Replicate heterogeneous app/main.py build_frame_bytes() exactly."""
    s = sorted(landmarks[:21], key=lambda lm: lm[0])
    wx, wy = s[0][1], s[0][2]
    md = max(
        (max(abs(lm[1] - wx), abs(lm[2] - wy)) for lm in s),
        default=1
    ) or 1
    frame = bytearray()
    for lm in s:
        nx = max(0, min(65535, int(((lm[1] - wx) / md + 1) * 32767)))
        ny = max(0, min(65535, int(((lm[2] - wy) / md + 1) * 32767)))
        frame.append(lm[0] & 0x1F)
        frame.append((nx >> 8) & 0xFF)
        frame.append(nx & 0xFF)
        frame.append((ny >> 8) & 0xFF)
        frame.append(ny & 0xFF)
    return frame  # 105 bytes


class HeterogeneousBenchmark:
    def __init__(self, num_samples, port, baud, device, display, ack_timeout):
        self.num_samples  = num_samples
        self.port         = port
        self.baud         = baud
        self.device       = device
        self.display      = display
        self.ack_timeout  = ack_timeout
        self.uart_floor   = _uart_floor_ms(baud)
        self.data         = defaultdict(list)

        self.tracker = HandTracker()

        print(f"[HeterogeneousBenchmark] Opening {port} @ {baud} baud …")
        self.ser = serial.Serial(port, baud, timeout=ack_timeout)
        try:
            self.ser.set_low_latency_mode(True)
        except Exception:
            pass
        time.sleep(2)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        print(f"  UART theoretical floor : {self.uart_floor:.3f} ms")

    def run(self) -> int:
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            sys.exit(f"[ERROR] Cannot open camera device {self.device}")

        print(f"\n  Collecting {self.num_samples} valid samples …")
        print("  Show different hand gestures. Press Q to abort.\n")

        n = 0
        no_ack = 0

        while n < self.num_samples:
            #  Stage 1 : Camera Capture 
            t0 = time.perf_counter()
            ok, frame = cap.read()
            t1 = time.perf_counter()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            capture_ms = (t1 - t0) * 1e3

            #  Stage 2 : MediaPipe Detection 
            t2 = time.perf_counter()
            frame = self.tracker.find_hands(frame, draw=False)
            landmarks, _ = self.tracker.get_landmarks(frame)
            t3 = time.perf_counter()
            mediapipe_ms = (t3 - t2) * 1e3

            if len(landmarks) < 21:
                if self.display:
                    cv2.imshow("Benchmark – Heterogeneous", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue

            #  Stage 3 : Serialisation 
            t4 = time.perf_counter()
            payload = build_frame_bytes(landmarks)
            t5 = time.perf_counter()
            serial_ms = (t5 - t4) * 1e3

            #  Stage 4 : UART TX 
            self.ser.reset_input_buffer()
            t6 = time.perf_counter()
            self.ser.write(payload)
            self.ser.flush()
            t7 = time.perf_counter()
            uart_tx_ms = (t7 - t6) * 1e3

            #  Stage 5 : FPGA Pipeline + UART RX 
            t8 = time.perf_counter()
            ack = self.ser.read(1)
            t9 = time.perf_counter()
            fpga_rx_ms = (t9 - t8) * 1e3

            if len(ack) != 1:
                no_ack += 1
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                if no_ack >= 5:
                    print("[WARN] 5 consecutive ACK timeouts – check FPGA & cable.")
                    no_ack = 0
                continue
            no_ack = 0

            gesture_id   = ack[0] & 0x07
            gesture_name = GESTURE_NAMES.get(gesture_id, f"id={gesture_id}")
            fpga_only_ms = max(0.0, fpga_rx_ms - self.uart_floor)

            #  Stage 6 : Command Mapping 
            t10 = time.perf_counter()
            cmd = GESTURE_COMMANDS.get(gesture_name)
            _   = VLC_KEYS.get(cmd) if cmd else None
            t11 = time.perf_counter()
            cmd_ms = (t11 - t10) * 1e3

            total_ms = (capture_ms + mediapipe_ms + serial_ms
                        + uart_tx_ms + fpga_rx_ms + cmd_ms)

            self.data["capture_ms"].append(capture_ms)
            self.data["mediapipe_ms"].append(mediapipe_ms)
            self.data["serialise_ms"].append(serial_ms)
            self.data["uart_tx_ms"].append(uart_tx_ms)
            self.data["fpga_and_rx_ms"].append(fpga_rx_ms)
            self.data["fpga_only_ms"].append(fpga_only_ms)
            self.data["command_mapping_ms"].append(cmd_ms)
            self.data["total_ms"].append(total_ms)
            self.data["gesture"].append(gesture_name)
            self.data["wall_time"].append(t11)

            n += 1
            if n % 50 == 0:
                print(f"  [{n:4d}/{self.num_samples}]  "
                      f"total={total_ms:6.2f}ms  fpga≈{fpga_only_ms:5.2f}ms  "
                      f"uart_tx={uart_tx_ms:5.2f}ms  gesture={gesture_name}")

            if self.display:
                cv2.putText(frame, f"[BENCH] {gesture_name}  {total_ms:.1f}ms",
                            (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
                cv2.imshow("Benchmark – Heterogeneous (Q=quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        self.ser.close()
        cv2.destroyAllWindows()
        return n

    def compute_stats(self) -> dict:
        stages = ["capture_ms","mediapipe_ms","serialise_ms",
                  "uart_tx_ms","fpga_and_rx_ms","fpga_only_ms",
                  "command_mapping_ms","total_ms"]
        per_stage = {s: _stats(np.array(self.data[s])) for s in stages}

        total = np.array(self.data["total_ms"])
        fps   = 1000.0 / np.mean(total) if np.mean(total) > 0 else 0

        uart_stages   = ["uart_tx_ms","fpga_and_rx_ms"]
        uart_overhead = sum(np.mean(self.data[s]) for s in uart_stages)
        total_mean    = np.mean(total)

        unique, counts = np.unique(self.data["gesture"], return_counts=True)

        return {
            "system": {
                "architecture":     "Heterogeneous – Jetson + Nexys4DDR FPGA",
                "source_repo":      "heterogeneous_system",
                "serial_port":      self.port,
                "baud_rate":        self.baud,
                "uart_floor_ms":    self.uart_floor,
                "total_samples":    len(total),
            },
            "summary": {
                "fps":                  float(fps),
                "mean_latency_ms":      float(total_mean),
                "uart_overhead_ms":     float(uart_overhead),
                "uart_overhead_pct":    float(uart_overhead / total_mean * 100),
                "jitter":               _jitter(total),
            },
            "per_stage_stats": per_stage,
            "gesture_distribution": {g: int(c) for g, c in zip(unique, counts)},
            "raw_data": {
                k: [float(v) for v in self.data[k]]
                for k in stages
            },
            "gesture_sequence": self.data["gesture"],
        }

    def save(self, stats: dict, ts: str) -> tuple:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        base  = f"heterogeneous_latency_{ts}"
        jpath = os.path.join(RESULTS_DIR, base + ".json")
        cpath = os.path.join(RESULTS_DIR, base + ".csv")

        with open(jpath, "w") as f:
            json.dump(stats, f, indent=2)

        stages = ["capture_ms","mediapipe_ms","serialise_ms",
                  "uart_tx_ms","fpga_and_rx_ms","fpga_only_ms",
                  "command_mapping_ms","total_ms"]
        n = len(self.data["total_ms"])
        with open(cpath, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sample_idx"] + stages + ["gesture"])
            for i in range(n):
                row = [i] + [round(self.data[s][i], 4) for s in stages] \
                    + [self.data["gesture"][i]]
                w.writerow(row)

        return jpath, cpath

    def print_summary(self, stats: dict):
        s  = stats["per_stage_stats"]
        sm = stats["summary"]
        uf = self.uart_floor
        sep = "=" * 72
        print(f"\n{sep}")
        print("  HETEROGENEOUS BENCHMARK  -  Jetson Orin Nano + Nexys4DDR FPGA")
        print(sep)
        print(f"\n{'Stage':<32} {'Mean':>8} {'Std':>8} {'P95':>8} {'Max':>8}")
        print("-" * 72)
        labels = {
            "capture_ms":          "Camera Capture",
            "mediapipe_ms":        "MediaPipe Detection",
            "serialise_ms":        "Landmark Serialisation",
            "uart_tx_ms":          "UART TX  (105 bytes)",
            "fpga_and_rx_ms":      "FPGA Pipeline + UART RX",
            "fpga_only_ms":        "  └─ FPGA only (est.)",
            "command_mapping_ms":  "Command Mapping",
            "total_ms":            "TOTAL END-TO-END",
        }
        for key, name in labels.items():
            d = s[key]
            print(f"  {name:<30} {d['mean']:>7.2f}ms {d['std']:>7.2f}ms "
                  f"{d['p95']:>7.2f}ms {d['max']:>7.2f}ms")
        print("-" * 72)
        print(f"\n  UART theoretical floor : {uf:.3f} ms")
        print(f"  UART overhead total    : {sm['uart_overhead_ms']:.2f} ms  "
              f"({sm['uart_overhead_pct']:.1f}% of pipeline)")
        print(f"\n  Effective FPS          : {sm['fps']:.2f} fps")
        print(f"  Mean Latency           : {sm['mean_latency_ms']:.2f} ms")
        print(f"  Mean Jitter            : {sm['jitter']['mean_abs_ms']:.2f} ms")
        print(f"  Target ≥15 FPS         : {'PASS ' if sm['fps'] >= 15 else 'FAIL '}")
        print(f"  Target <200 ms         : "
              f"{'PASS ' if sm['mean_latency_ms'] < 200 else 'FAIL '}")
        print(sep + "\n")


def main():
    ap = argparse.ArgumentParser(
        description="Heterogeneous (Jetson+FPGA) pipeline latency benchmark.")
    ap.add_argument("--samples",     type=int,   default=500)
    ap.add_argument("--port",        type=str,   default="/dev/ttyUSB1",
                    help="Serial port connected to FPGA (default: /dev/ttyUSB1)")
    ap.add_argument("--baud",        type=int,   default=115200)
    ap.add_argument("--device",      type=int,   default=0,
                    help="Camera device index (default: 0)")
    ap.add_argument("--ack-timeout", type=float, default=0.5,
                    help="UART read timeout in seconds (default: 0.5)")
    ap.add_argument("--no-display",  action="store_true")
    args = ap.parse_args()

    bench = HeterogeneousBenchmark(
        num_samples=args.samples,
        port=args.port,
        baud=args.baud,
        device=args.device,
        display=not args.no_display,
        ack_timeout=args.ack_timeout,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    n  = bench.run()
    if n == 0:
        sys.exit("No samples collected.")

    stats = bench.compute_stats()
    bench.print_summary(stats)
    j, c = bench.save(stats, ts)
    print(f"  Results → {j}")
    print(f"  Results → {c}\n")


if __name__ == "__main__":
    main()
