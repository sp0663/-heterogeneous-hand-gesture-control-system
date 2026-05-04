"""
Launches tegrastats (or falls back to jtop JSON API) and parses its output
stream into structured JSON + CSV logs containing:

  - Wall-clock timestamp
  - Per-CPU-core utilisation (%)
  - Total RAM used / total (MB)
  - GPU utilisation (%)
  - GPU memory used / total (MB)
  - Power rails: CPU, GPU, SOC, total (Watts)
  - Die temperature (°C) – if present

tegrastats output format reference (Jetson Orin Nano):
  RAM 1234/7772MB (lfb 256x4MB) SWAP 0/3886MB (cached 0MB)
  CPU [12%@998,8%@998,...] EMC_FREQ 0%@2133 GPC_FREQ 0%@0
  AO@34.5C CPU@36C GPU@35.5C tj@36C
  VDD_IN 2543mW/2543mW VDD_CPU_GPU_CV 368mW/368mW VDD_SOC 623mW/623mW

Usage
-----
    # Run alongside a benchmark script (in a second terminal):
    python parse_tegrastats.py --duration 120 --interval 500 --tag hetero_run1
    python parse_tegrastats.py --duration 120 --interval 500 --tag homo_run1

    # Or using jtop (if jetson-stats installed):
    python parse_tegrastats.py --backend jtop --duration 120 --tag homo_run1
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# tegrastats line parser

_RE_RAM      = re.compile(r'RAM\s+(\d+)/(\d+)MB')
_RE_SWAP     = re.compile(r'SWAP\s+(\d+)/(\d+)MB')
_RE_CPU      = re.compile(r'CPU\s+\[([^\]]+)\]')
_RE_GPU_FREQ = re.compile(r'GPC_FREQ\s+(\d+)%@(\d+)')
_RE_EMC      = re.compile(r'EMC_FREQ\s+(\d+)%@(\d+)')
_RE_TEMP     = re.compile(r'(\w+)@([\d.]+)C')
_RE_POWER    = re.compile(r'(VDD_\w+)\s+(\d+)mW/(\d+)mW')
_RE_CPU_CORE = re.compile(r'(\d+)%@(\d+)')


def parse_line(line: str, wall_time: float) -> Optional[Dict]:
    """Parse one tegrastats output line into a structured dict."""
    line = line.strip()
    if not line:
        return None

    rec: dict = {"wall_time": wall_time, "raw": line}

    # RAM
    m = _RE_RAM.search(line)
    if m:
        rec["ram_used_mb"]  = int(m.group(1))
        rec["ram_total_mb"] = int(m.group(2))
        rec["ram_util_pct"] = round(int(m.group(1)) / int(m.group(2)) * 100, 2)

    # SWAP
    m = _RE_SWAP.search(line)
    if m:
        rec["swap_used_mb"]  = int(m.group(1))
        rec["swap_total_mb"] = int(m.group(2))

    # Per-core CPU
    m = _RE_CPU.search(line)
    if m:
        cores = _RE_CPU_CORE.findall(m.group(1))
        rec["cpu_cores"] = [
            {"core": i, "util_pct": int(util), "freq_mhz": int(freq)}
            for i, (util, freq) in enumerate(cores)
        ]
        utils = [int(u) for u, _ in cores]
        rec["cpu_mean_util_pct"] = round(sum(utils) / len(utils), 2) if utils else 0
        rec["cpu_max_util_pct"]  = max(utils) if utils else 0

    # GPU
    m = _RE_GPU_FREQ.search(line)
    if m:
        rec["gpu_util_pct"] = int(m.group(1))
        rec["gpu_freq_mhz"] = int(m.group(2))

    # EMC (memory controller)
    m = _RE_EMC.search(line)
    if m:
        rec["emc_util_pct"] = int(m.group(1))
        rec["emc_freq_mhz"] = int(m.group(2))

    # Temperatures
    temps = {name: float(val) for name, val in _RE_TEMP.findall(line)
             if name not in ("VDD", "mW")}
    if temps:
        rec["temperatures_c"] = temps

    # Power rails
    power_rails = {}
    for name, current, average in _RE_POWER.findall(line):
        power_rails[name] = {
            "current_mw": int(current),
            "average_mw": int(average),
            "current_w":  round(int(current) / 1000, 3),
            "average_w":  round(int(average) / 1000, 3),
        }
    if power_rails:
        rec["power_rails"] = power_rails
        rec["total_power_w"] = round(
            sum(v["current_w"] for v in power_rails.values()), 3
        )
        # Identify CPU/GPU rails
        for key in power_rails:
            lk = key.lower()
            if "cpu" in lk:
                rec["cpu_power_w"] = power_rails[key]["current_w"]
            if "gpu" in lk or "cv" in lk:
                rec["gpu_power_w"] = power_rails[key]["current_w"]
            if "soc" in lk:
                rec["soc_power_w"] = power_rails[key]["current_w"]

    return rec


# tegrastats backend

class TegrastatsLogger:
    def __init__(self, interval_ms: int, duration_s: float, tag: str):
        self.interval_ms = interval_ms
        self.duration_s  = duration_s
        self.tag         = tag
        self.records: List[Dict] = []
        self._stop = threading.Event()

    def run(self):
        cmd = ["tegrastats", f"--interval={self.interval_ms}"]
        print(f"[parse_tegrastats] Launching: {' '.join(cmd)}")
        t_start = time.perf_counter()
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except FileNotFoundError:
            sys.exit("[ERROR] 'tegrastats' not found. Ensure you are on a Jetson "
                     "with NVIDIA Jetpack installed, or use --backend jtop.")

        try:
            for line in proc.stdout:
                wall = time.perf_counter() - t_start
                rec  = parse_line(line, wall)
                if rec:
                    self.records.append(rec)
                if wall >= self.duration_s:
                    break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

        print(f"  Collected {len(self.records)} tegrastats samples.")


# jtop backend

class JtopLogger:
    def __init__(self, interval_ms: int, duration_s: float, tag: str):
        self.interval_ms = interval_ms
        self.duration_s  = duration_s
        self.tag         = tag
        self.records: List[Dict] = []

    def run(self):
        try:
            from jtop import jtop
        except ImportError:
            sys.exit("[ERROR] jtop not installed. Run: pip install jetson-stats")

        print(f"[parse_tegrastats] Using jtop backend …")
        t_start = time.perf_counter()
        with jtop(interval=self.interval_ms / 1000) as jetson:
            while jetson.ok():
                wall = time.perf_counter() - t_start
                rec  = {"wall_time": wall}

                # CPU
                cpus = jetson.cpu
                utils = [cpus[k]["val"] for k in cpus if isinstance(cpus[k], dict)
                         and "val" in cpus[k]]
                rec["cpu_cores"] = [
                    {"core": i, "util_pct": v} for i, v in enumerate(utils)
                ]
                rec["cpu_mean_util_pct"] = round(sum(utils)/len(utils), 2) if utils else 0
                rec["cpu_max_util_pct"]  = max(utils) if utils else 0

                # GPU
                gpu = jetson.gpu
                if isinstance(gpu, dict) and "val" in gpu:
                    rec["gpu_util_pct"] = gpu["val"]

                # RAM
                ram = jetson.memory.get("RAM", {})
                if ram:
                    rec["ram_used_mb"]  = ram.get("used", 0)
                    rec["ram_total_mb"] = ram.get("tot",  0)

                # Power
                power = jetson.power
                if isinstance(power, dict):
                    rec["power_rails"] = {}
                    total = 0
                    for name, val in power.items():
                        if isinstance(val, dict) and "power" in val:
                            mw = val["power"]
                            rec["power_rails"][name] = {
                                "current_mw": mw,
                                "current_w":  round(mw/1000, 3),
                            }
                            total += mw
                    rec["total_power_w"] = round(total / 1000, 3)

                # Temps
                temps = jetson.temperature
                if isinstance(temps, dict):
                    rec["temperatures_c"] = {
                        k: v for k, v in temps.items()
                        if isinstance(v, (int, float))
                    }

                self.records.append(rec)
                if wall >= self.duration_s:
                    break

        print(f"  Collected {len(self.records)} jtop samples.")


# Statistics + save

def _compute_power_stats(records: List[Dict]) -> Dict:
    def _field(key):
        vals = [r[key] for r in records if key in r]
        if not vals:
            return None
        import statistics
        return {
            "mean_w":   round(sum(vals)/len(vals), 3),
            "min_w":    round(min(vals), 3),
            "max_w":    round(max(vals), 3),
            "std_w":    round(statistics.stdev(vals) if len(vals) > 1 else 0, 3),
        }
    return {
        "total_power": _field("total_power_w"),
        "cpu_power":   _field("cpu_power_w"),
        "gpu_power":   _field("gpu_power_w"),
        "soc_power":   _field("soc_power_w"),
    }


def save_results(records: list[dict], tag: str, ts: str, backend: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    base  = f"tegrastats_{tag}_{ts}"
    jpath = os.path.join(RESULTS_DIR, base + ".json")
    cpath = os.path.join(RESULTS_DIR, base + ".csv")

    output = {
        "metadata": {
            "tag":     tag,
            "backend": backend,
            "samples": len(records),
        },
        "power_summary":  _compute_power_stats(records),
        "records":        records,
    }

    with open(jpath, "w") as f:
        json.dump(output, f, indent=2)

    # Flatten to CSV
    flat_keys = ["wall_time","ram_used_mb","ram_total_mb","ram_util_pct",
                 "cpu_mean_util_pct","cpu_max_util_pct",
                 "gpu_util_pct","emc_util_pct",
                 "total_power_w","cpu_power_w","gpu_power_w","soc_power_w"]
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=flat_keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)

    print(f"\n  JSON → {jpath}")
    print(f"  CSV  → {cpath}")
    return jpath, cpath


def print_power_summary(records: list[dict]):
    stats = _compute_power_stats(records)
    print("\n" + "="*52)
    print("  POWER & RESOURCE SUMMARY")
    print("="*52)
    for name, s in stats.items():
        if s:
            print(f"  {name:<18}  mean={s['mean_w']:6.3f}W  "
                  f"max={s['max_w']:6.3f}W  std={s['std_w']:5.3f}W")
    # CPU
    cpu_vals = [r["cpu_mean_util_pct"] for r in records if "cpu_mean_util_pct" in r]
    if cpu_vals:
        print(f"  {'cpu_mean_util':<18}  mean={sum(cpu_vals)/len(cpu_vals):5.1f}%  "
              f"max={max(cpu_vals):5.1f}%")
    gpu_vals = [r["gpu_util_pct"] for r in records if "gpu_util_pct" in r]
    if gpu_vals:
        print(f"  {'gpu_util':<18}  mean={sum(gpu_vals)/len(gpu_vals):5.1f}%  "
              f"max={max(gpu_vals):5.1f}%")
    print("="*52 + "\n")


def main():
    ap = argparse.ArgumentParser(
        description="Log Jetson power/resource metrics via tegrastats or jtop.")
    ap.add_argument("--duration",  type=float, default=60.0,
                    help="Logging duration in seconds (default: 60)")
    ap.add_argument("--interval",  type=int,   default=500,
                    help="Sampling interval in ms (default: 500)")
    ap.add_argument("--tag",       type=str,   default="run",
                    help="Label for output filenames (e.g. homo_run1)")
    ap.add_argument("--backend",   choices=["tegrastats","jtop"],
                    default="tegrastats",
                    help="Data source backend (default: tegrastats)")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[parse_tegrastats] backend={args.backend}  "
          f"duration={args.duration}s  interval={args.interval}ms  tag={args.tag}")

    if args.backend == "jtop":
        logger = JtopLogger(args.interval, args.duration, args.tag)
    else:
        logger = TegrastatsLogger(args.interval, args.duration, args.tag)

    logger.run()

    if not logger.records:
        sys.exit("[ERROR] No records collected.")

    print_power_summary(logger.records)
    save_results(logger.records, args.tag, ts, args.backend)


if __name__ == "__main__":
    main()
