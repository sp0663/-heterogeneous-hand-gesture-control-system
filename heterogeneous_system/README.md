# Heterogeneous Hand Gesture Control System

A real-time hand gesture recognition system built on a heterogeneous computing architecture, combining an **NVIDIA Jetson Nano** for landmark detection and an **FPGA** for low-latency, rule-based gesture classification.

---

## Overview

This project splits the gesture recognition pipeline across two processors to leverage the strengths of each:

- **Jetson Nano** — runs a neural network-based hand landmark detector (e.g. MediaPipe) on its GPU/CPU, extracting 21 3D keypoints from a camera frame.
- **FPGA** — receives the landmark coordinates over UART and applies a custom rule-based classification engine implemented in Verilog to identify the gesture in hardware.

This heterogeneous approach achieves deterministic, low-latency classification while keeping the computationally heavy ML inference on a capable host processor.

---

## System Architecture

```
┌─────────────────────────────┐         UART           ┌──────────────────────────────────────┐
        Jetson Nano             ──────────────────▶                  FPGA
                                                     
  Camera → MediaPipe              21 landmarks (x,y)        UART RX → Landmark Storage
  Hand Landmark Detection                                 → Feature Extraction      
                                ◀────────────────        → Rule-Based Classifier   
  Receives gesture ID             gesture_id (4-bit)      → UART TX                 
└─────────────────────────────┘                        └──────────────────────────────────────┘
```

---

## FPGA Pipeline (Verilog Modules)

The FPGA design is structured as a sequential processing pipeline:

| Module | File | Description |
|---|---|---|
| **UART RX** | `uart_rx.v` | Low-level serial receiver |
| **Baud Generator** | `baud_generator.v` | Clock divider for UART timing |
| **Landmark Storage** | `landmark_storage.v` | Buffers all 21 (x, y) coordinates until a full frame is ready |
| **Landmark Distance** | `landmark_distance.v` | Computes Euclidean distances between keypoints |
| **Angle Calculator** | `angle_calculator.v` | Computes joint angles between landmark triplets |
| **Feature Extractor** | `feature_extractor.v` | Aggregates distances and angles into a feature vector |
| **Gesture Classifier** | `gesture_classifier.v` | Applies rule-based logic to map features to a gesture ID |
| **UART TX** | `uart_tx.v` | Low-level serial transmitter |
| **Top Level** | `gesture_system_top.v` | Wires all modules together |

### Data Flow

```
uart_rx → frame_sync / packet_formatter
        → landmark_storage (buffers 21 landmarks)
        → feature_extractor
            ├── landmark_distance  (inter-keypoint distances)
            └── angle_calculator   (joint angles)
        → gesture_classifier       (rule-based decision)
        → output_interface → uart_tx
```

---

## Communication Protocol

Landmark data is streamed from the Jetson Nano to the FPGA over **UART**. Each packet encodes a landmark ID (0–20) along with its x and y coordinates. After all 21 landmarks are received, the FPGA asserts `frame_ready` and begins classification.

The classified gesture ID (4-bit) is sent back to the Jetson Nano over a second UART line.

---

## Gesture Classification

Classification is **rule-based** — no neural network runs on the FPGA. Instead, the classifier evaluates geometric conditions on the extracted features:

- **Finger extension** — determined by comparing joint angles along each finger
- **Inter-landmark distances** — e.g. fingertip-to-palm distances to distinguish open/closed hand states
- **Relative positions** — e.g. thumb position relative to index finger for gestures like pinch

This approach gives deterministic, cycle-accurate latency with minimal FPGA resource usage.

---

## Hardware Requirements

| Component | Details |
|---|---|
| Host processor | NVIDIA Jetson Nano |
| FPGA | Any Verilog-compatible FPGA (e.g. Xilinx, Altera/Intel) |
| Camera | USB or CSI camera connected to Jetson Nano |
| Interface | UART (3.3V logic — check level shifting if required) |

---

## Software Requirements (Jetson Nano)

- Python 3.x
- [MediaPipe](https://mediapipe.dev/) — hand landmark detection
- OpenCV — camera capture
- `pyserial` — UART communication

---

## Getting Started

### 1. Synthesize the FPGA design

Import all `.v` files into your FPGA toolchain (Vivado, Quartus, etc.) with `gesture_system_top.v` as the top-level module. Configure the baud rate in `baud_generator.v` to match your UART setup.

### 2. Set up the Jetson Nano

Install dependencies:

```bash
pip install mediapipe opencv-python pyserial
```

Connect the Jetson's UART TX/RX pins to the FPGA's RX/TX pins respectively.

### 3. Run landmark streaming

On the Jetson, run your landmark detection script. For each frame, serialize the 21 landmark (x, y) pairs and transmit them over UART to the FPGA using the packet format expected by `frame_sync.v`.

### 4. Read gesture output

The FPGA will respond with a 4-bit gesture ID over UART after each classified frame. Read and act on this in your Jetson-side application.

---

## Repository Structure

```
heterogeneous_hand_gesture_control_system/
├── gesture_system_top.v      # Top-level module
├── uart_rx.v                 # UART receiver
├── uart_tx.v                 # UART transmitter
├── baud_generator.v          # Baud rate clock divider
├── landmark_storage.v        # Landmark frame buffer
├── landmark_distance.v       # Distance computation
├── angle_calculator.v        # Angle computation
├── feature_extractor.v       # Feature aggregation
└── gesture_classifier.v      # Rule-based classifier
```

---

## Design Rationale

**Why split across Jetson + FPGA?**
Neural network inference for landmark detection is GPU-friendly and changes frequently during development — a good fit for the Jetson. Gesture classification from landmarks is a fixed, latency-sensitive operation with simple arithmetic — ideal for FPGA hardware.

**Why rule-based classification on the FPGA?**
A rule-based approach avoids the cost of implementing a neural network inference engine in RTL. Geometric rules over hand landmark positions are surprisingly effective for a well-defined gesture vocabulary, and they run in a deterministic number of clock cycles.

---

## Collaborators

* **Sri Prahlad Mukunthan**
* **Rushil Jain**
* **Shresh Parti**

