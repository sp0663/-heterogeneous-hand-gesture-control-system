# Gesture Media Controller

Touchless HCI for Media Control Using Hand Gestures on NVIDIA Jetson Nano.

---

## How to Operate the Program

To interact with the system, train models, or map gestures, you **must run the `app_ui.py` file**. This serves as the central graphical control hub for the entire application. 

**1. Install Dependencies**
First, ensure all required libraries are installed:
`pip install -r req.txt`

**2. Launch the Application**
Open your terminal and run the UI file:
`python app_ui.py`

**3. Train Custom ML Gestures (Optional)**
If you want to add your own custom gestures:
* Click **"Train New Gestures"** in the UI.
* Type the name of your gesture in the terminal and hold it in front of the camera to record 300 coordinate samples.
> **CRUCIAL REQUIREMENT:** You MUST always record a "background" or "neutral" gesture during this process! This teaches the machine learning model what your hand looks like when you are *not* doing a specific command, preventing random hand movements from triggering VLC.

**4. Map Gestures to VLC**
Once your gestures are trained, you need to link them to VLC actions:
* Select your trained gesture from the left dropdown.
* Select the VLC action you want it to trigger from the right dropdown.
* Click **"Save Mapping to Config"**.
> **ADDING MULTIPLE GESTURES:** If you trained 2 or more custom gestures, you must select and click "Save Mapping to Config" **as many times as there are gestures** (once for each specific gesture). 

**5. Start Controlling!**
Click the green **"Launch Controller"** button. Show your gestures to the camera to control your media!

---

## Standard Built-in Gestures

If you don't want to train custom gestures, the system comes fully equipped with highly optimized, mathematical rule-based gestures out of the box:

| Gesture | Action | Keys Pressed |
| :--- | :--- | :--- |
| **Index Finger Extended** | **System Enable / Disable** | No key |
| **Open Palm** | Play / Pause | Space |
| **Fist** | Mute / Unmute | m |
| **Pinch** | Toggle Fullscreen | f |
| **Swipe Left** | Move Previous | p |
| **Swipe Right** | Move Next | n |
| **Fist Up / Down** | Volume Up / Down | Ctrl+Up / Ctrl+Down |
| **Pinch Rotate** (Clock / Anti) | Jump Forward / Backward | Alt+Right / Alt+Left |

---

## System Features & Architecture

* **The Safety Toggle:** Point your index finger to completely disable the controller. The system will not execute any gesture until the index finger is detected again, preventing false triggers.
* **Hybrid Recognition:** Utilizes pure geometric math for high-speed dynamic movements and an automated Random Forest ML pipeline for recognizing complex, user-defined static poses.
* **Dynamic Accumulators:** Actions like changing volume or seeking through a video use tracking accumulators. This allows you to precisely control media by dragging your fist up/down or twisting your pinch.

---

## Hardware & Software Stack

* **Hardware Platform:** NVIDIA Jetson Orin Nano
* **Camera Input:** USB 3.2 Gen 2 interface for real-time video capture
* **Operating System:** Jetpack OS
* **Language:** Python 3.10
* **Hand Tracking:** MediaPipe Hands v0.10
* **Computer Vision:** OpenCV 4.5+
* **Machine Learning:** Scikit-learn (Random Forest Classifier)
* **Input Emulation:** pynput
* **UI Framework:** tkinter

---

## Performance Metrics

* **Accuracy:** ~95.1% overall system accuracy in controlled lighting.
* **Latency:** ~110ms average end-to-end latency (45% below the 200ms target).
* **Frame Rate:** ~22 FPS average (46% above the 15 FPS target).
* **Resource Utilization:** CPU at 25-35%, GPU at 45-60%, Power consumption 7-9W.

---

## Collaborators

* **Sri Prahlad Mukunthan**
* **Rushil Jain**
* **Shresh Parti**
* **College:** National Institute of Technology, Karnataka
* **College Mentor:** Dr. Sumam David
