"""
Full-pipeline latency + throughput benchmark for the pure-Jetson
homogeneous_system (Jetson-only architecture).

Pipeline stages timed with time.perf_counter():
  1. Camera Capture
  2. MediaPipe Hand Detection  (find_hands + get_landmarks)
  3. Gesture Recognition       (GestureRecogniser.recognise_gesture)
  4. Command Mapping Lookup

Outputs
-------
  results/homogeneous_latency_<timestamp>.json
  results/homogeneous_latency_<timestamp>.csv

Usage
-----
    cd comparative_benchmarks/
    python benchmark_homogeneous.py [--samples 500] [--device 0] [--no-display]
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

#  Path resolution 
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_HOMO_DIR  = os.path.join(_REPO_ROOT, "homogeneous_system")
sys.path.insert(0, _HOMO_DIR)

from gesture_recogniser import GestureRecogniser
from hand_tracker       import HandTracker
from config             import GESTURE_COMMANDS, VLC_KEYS

#  Constants 
UART_THEORETICAL_FLOOR_MS = 0.0   # No UART in homogeneous system
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


#  Statistics helpers 

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


def _jitter(total_arr: np.ndarray) -> dict:
    diffs = np.diff(total_arr)
    return {
        "mean_abs_ms": float(np.mean(np.abs(diffs))),
        "std_ms":      float(np.std(diffs)),
        "max_abs_ms":  float(np.max(np.abs(diffs))),
    }


#  Benchmark core 

class HomogeneousBenchmark:
    def __init__(self, num_samples: int, device: int, display: bool):
        self.num_samples = num_samples
        self.device      = device
        self.display     = display
        self.data        = defaultdict(list)

        self.tracker = HandTracker()
        self.recon   = GestureRecogniser()

    def run(self) -> int:
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            sys.exit(f"[ERROR] Cannot open camera device {self.device}")

        print(f"\n[HomogeneousBenchmark] Collecting {self.num_samples} valid samples …")
        print("  Show hand gestures in front of the camera.")
        print("  Press Q to abort early.\n")

        sample_count = 0

        while sample_count < self.num_samples:
            #  Stage 1 : Camera Capture 
            t0 = time.perf_counter()
            success, frame = cap.read()
            t1 = time.perf_counter()
            if not success:
                continue
            frame = cv2.flip(frame, 1)
            capture_ms = (t1 - t0) * 1e3

            #  Stage 2 : MediaPipe Hand Detection 
            t2 = time.perf_counter()
            frame = self.tracker.find_hands(frame, draw=False)
            landmarks, hand_label = self.tracker.get_landmarks(frame)
            t3 = time.perf_counter()
            mediapipe_ms = (t3 - t2) * 1e3

            if not landmarks:
                if self.display:
                    cv2.imshow("Benchmark – Homogeneous", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue

            #  Stage 3 : Gesture Recognition 
            t4 = time.perf_counter()
            gesture = self.recon.recognise_gesture(landmarks, hand_label, frame)
            t5 = time.perf_counter()
            recognition_ms = (t5 - t4) * 1e3

            #  Stage 4 : Command Mapping Lookup 
            t6 = time.perf_counter()
            command = GESTURE_COMMANDS.get(gesture)
            _ = VLC_KEYS.get(command) if command else None
            t7 = time.perf_counter()
            command_ms = (t7 - t6) * 1e3

            #  Totals 
            total_ms = capture_ms + mediapipe_ms + recognition_ms + command_ms

            self.data["capture_ms"].append(capture_ms)
            self.data["mediapipe_ms"].append(mediapipe_ms)
            self.data["recognition_ms"].append(recognition_ms)
            self.data["command_mapping_ms"].append(command_ms)
            self.data["total_ms"].append(total_ms)
            self.data["gesture"].append(gesture)
            self.data["wall_time"].append(t7)

            sample_count += 1

            if sample_count % 50 == 0:
                print(f"  [{sample_count:4d}/{self.num_samples}]  "
                      f"total={total_ms:6.2f} ms  "
                      f"mediapipe={mediapipe_ms:6.2f} ms  "
                      f"gesture={gesture}")

            if self.display:
                cv2.putText(frame, f"[BENCH] {gesture}  {total_ms:.1f}ms",
                            (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                cv2.imshow("Benchmark – Homogeneous (Q=quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        cap.release()
        cv2.destroyAllWindows()
        return sample_count

    def compute_stats(self) -> dict:
        stages = ["capture_ms", "mediapipe_ms", "recognition_ms",
                  "command_mapping_ms", "total_ms"]
        per_stage = {}
        for s in stages:
            per_stage[s] = _stats(np.array(self.data[s]))

        total_arr = np.array(self.data["total_ms"])
        fps = 1000.0 / np.mean(total_arr) if np.mean(total_arr) > 0 else 0.0

        gestures  = self.data["gesture"]
        unique, counts = np.unique(gestures, return_counts=True)
        gesture_dist = {g: int(c) for g, c in zip(unique, counts)}

        return {
            "system": {
                "architecture":   "Homogeneous – Jetson Only",
                "source_repo":    "homogeneous_system",
                "camera_device":  self.device,
                "total_samples":  len(total_arr),
            },
            "summary": {
                "fps":             float(fps),
                "mean_latency_ms": float(np.mean(total_arr)),
                "jitter":          _jitter(total_arr),
            },
            "per_stage_stats": per_stage,
            "gesture_distribution": gesture_dist,
            "raw_data": {
                k: [float(v) for v in self.data[k]]
                for k in stages
            },
            "gesture_sequence": gestures,
        }

    def save(self, stats: dict, timestamp: str) -> tuple:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        base = f"homogeneous_latency_{timestamp}"
        json_path = os.path.join(RESULTS_DIR, base + ".json")
        csv_path  = os.path.join(RESULTS_DIR, base + ".csv")

        with open(json_path, "w") as f:
            json.dump(stats, f, indent=2)

        stages = ["capture_ms","mediapipe_ms","recognition_ms",
                  "command_mapping_ms","total_ms"]
        n = len(self.data["total_ms"])
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sample_idx"] + stages + ["gesture"])
            for i in range(n):
                row = [i] + [round(self.data[s][i], 4) for s in stages] \
                    + [self.data["gesture"][i]]
                w.writerow(row)

        return json_path, csv_path

    def print_summary(self, stats: dict):
        s   = stats["per_stage_stats"]
        sm  = stats["summary"]
        sep = "=" * 68
        print(f"\n{sep}")
        print("  HOMOGENEOUS BENCHMARK  -  Jetson Orin Nano (Pure Software)")
        print(sep)
        print(f"\n{'Stage':<28} {'Mean':>8} {'Std':>8} {'P95':>8} {'Max':>8}")
        print("-" * 68)
        labels = {
            "capture_ms":          "Camera Capture",
            "mediapipe_ms":        "MediaPipe Detection",
            "recognition_ms":      "Gesture Recognition",
            "command_mapping_ms":  "Command Mapping",
            "total_ms":            "TOTAL END-TO-END",
        }
        for key, name in labels.items():
            d = s[key]
            print(f"  {name:<26} {d['mean']:>7.2f}ms {d['std']:>7.2f}ms "
                  f"{d['p95']:>7.2f}ms {d['max']:>7.2f}ms")
        print("-" * 68)
        print(f"\n  Effective FPS    : {sm['fps']:.2f} fps")
        print(f"  Mean Latency     : {sm['mean_latency_ms']:.2f} ms")
        print(f"  Mean Jitter      : {sm['jitter']['mean_abs_ms']:.2f} ms")
        print(f"  Max  Jitter      : {sm['jitter']['max_abs_ms']:.2f} ms")
        print(f"  Target ≥15 FPS   : {'PASS' if sm['fps'] >= 15 else 'FAIL'}")
        print(f"  Target <200 ms   : {'PASS' if sm['mean_latency_ms'] < 200 else 'FAIL'}")
        print(sep + "\n")


def main():
    ap = argparse.ArgumentParser(
        description="Homogeneous (pure-Jetson) pipeline latency benchmark.")
    ap.add_argument("--samples",    type=int, default=500,
                    help="Valid hand-detected frames to collect (default: 500)")
    ap.add_argument("--device",     type=int, default=0,
                    help="OpenCV camera device index (default: 0)")
    ap.add_argument("--no-display", action="store_true",
                    help="Suppress live preview window (faster, SSH-safe)")
    args = ap.parse_args()

    bench = HomogeneousBenchmark(
        num_samples=args.samples,
        device=args.device,
        display=not args.no_display,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    n  = bench.run()
    if n == 0:
        sys.exit("No samples collected. Ensure hand is visible to camera.")

    stats = bench.compute_stats()
    bench.print_summary(stats)
    j, c = bench.save(stats, ts)
    print(f"  Results → {j}")
    print(f"  Results → {c}\n")


if __name__ == "__main__":
    main()
