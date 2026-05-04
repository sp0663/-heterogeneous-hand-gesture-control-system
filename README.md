# Comparative Evaluation of Homogeneous and Heterogeneous Edge Architectures for Real-Time Hand Gesture Recognition

Mini-project, Department of Electronics and Communication Engineering,
National Institute of Technology Karnataka, Surathkal.

**Authors:** Shresh Parti, Sriprahlad Mukunthan, Rushil Jain
**Project Guide:** Dr. Sumam David S.

The full project report is provided in PDF form at the repository root.

## Overview

This work presents a controlled empirical comparison of two edge-computing architectures applied to real-time hand-gesture recognition for touchless media control:

1. A *homogeneous* implementation in which the entire pipeline — camera capture, MediaPipe hand-landmark detection, rule-based gesture classification, and command dispatch — executes on a single NVIDIA Jetson Orin Nano.
2. A *heterogeneous* implementation in which the Jetson performs only the vision stages and transmits the resulting 21-landmark coordinate frame over UART at 115200 baud to a Xilinx Artix-7 FPGA on a Digilent Nexys4 DDR board, where classification is performed in synthesised Verilog and a one-byte gesture identifier is returned to the host.

Each architecture was benchmarked over five 500-frame runs (three homogeneous, two heterogeneous), supplemented by a classifier-efficacy evaluation on a 200-sample static landmark dataset. The study quantifies end-to-end latency, per-stage timing, inter-frame jitter, per-class classification accuracy, FPGA resource utilisation, and total system power.

## Summary of Results

| Metric | Homogeneous | Heterogeneous |
| --- | --- | --- |
| Mean end-to-end latency | 38–42 ms | 51–60 ms |
| Effective frame rate | 24–27 FPS | 17–19 FPS |
| Classifier-stage latency | 0.94–1.11 ms (Python) | < 1 µs (Verilog) |
| Classifier-stage jitter (standard deviation) | 0.25 ms | 0 (cycle-deterministic) |
| Per-frame classifier accuracy | 94.26 % | 76.50 % |
| Total system power | 5.8 W | 4.7 W (−19 %) |
| FPGA on-chip power | — | 0.294 W |
| FPGA resource utilisation | — | 5.10 % LUTs, 31.67 % DSPs |

The FPGA classifier itself completes in approximately 100 ns at 50 MHz with no measurable jitter. The heterogeneous system's net latency penalty is attributable entirely to the UART communication overhead (~15 ms per frame); an analytical projection indicates that a migration to SPI at 10 MHz would reduce this overhead to 85 µs, yielding an end-to-end latency of 36.1 ms — 7.9 % lower than the homogeneous baseline. A detailed treatment is provided in the report.

## Repository Structure

```
.
├── homogeneous_system/                          Jetson-only implementation (Python).
├── heterogeneous_system/
│   ├── app/                                     Jetson-side application (Python).
│   ├── rtl/                                     Verilog RTL targeting the XC7A100T.
│   └── sim/                                     Verilog and Python testbenches.
├── benchmarks/
│   ├── benchmark_homogeneous.py                 End-to-end latency benchmark.
│   ├── benchmark_heterogeneous.py               End-to-end latency benchmark.
│   ├── benchmark_classifier_efficacy.py         Confusion matrix and P/R/F1 evaluation.
│   ├── generate_static_dataset.py               Synthetic-landmark dataset generator.
│   ├── parse_tegrastats.py                      Jetson power and utilisation logger.
│   └── results/                                 Benchmark outputs and Vivado reports.
└── Comparative_Evaluation_..._Recognition.pdf   Final report.
```

Subsystem-specific documentation is provided in the `README.md` of each subsystem folder.

## Hardware Requirements

* NVIDIA Jetson Orin Nano Developer Kit (8 GB)
* Digilent Nexys4 DDR with Xilinx Artix-7 XC7A100T-1CSG324C
* USB-A to micro-USB cable for the UART/programming link
* UVC-compliant USB webcam

## Software Requirements

The Jetson side was developed and tested on JetPack 6 (Ubuntu 22.04) with Python 3.10 or later. FPGA synthesis and implementation were performed in Xilinx Vivado 2024.1. Python dependencies are enumerated in the `req.txt` file of each system folder.

## Build and Execution

### Homogeneous System

```
cd homogeneous_system
pip install -r req.txt
python app_ui.py
```

### Heterogeneous System

1. Open the design in `heterogeneous_system/rtl/` in Vivado and run synthesis and implementation, or program the Nexys4 DDR directly with the prebuilt bitstream `heterogeneous_system/app/gesture_system_top.bit`.
2. Connect the Nexys4 DDR's USB-UART bridge to the Jetson and confirm the resulting device path (typically `/dev/ttyUSB1`). Update the `SERIAL_PORT` constant in `heterogeneous_system/app/main.py` if a different path is enumerated.
3. Launch the application:

   ```
   cd heterogeneous_system/app
   python main.py
   ```

Benchmark scripts may be invoked directly from the `benchmarks/` directory. All results are written to `benchmarks/results/`.

## Acknowledgements

The authors gratefully acknowledge the guidance of Dr. Sumam David S. and thank the Department of Electronics and Communication Engineering, NIT Karnataka, for providing access to the Jetson Orin Nano Developer Kit and the Nexys4 DDR development board. This work was undertaken as part of the Bharat AI-SoC Student Challenge.
