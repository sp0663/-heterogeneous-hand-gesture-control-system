import cv2
import serial
import time
from hand_tracker import HandTracker
from media_controller import MediaController
from config import GESTURE_HOLD_TIME, DEBUG

SERIAL_PORT  = "/dev/ttyUSB1"  # Update as needed (e.g., "COM8" on Windows)
BAUD_RATE    = 115200
ACK_TIMEOUT  = 0.5

GESTURE_NAMES = {
    0: "pinch",
    1: "fist",
    2: "open_palm",
    3: "index_finger",
    4: "unknown",
    5: "pinch_clockwise",
    6: "pinch_anticlockwise"
}

# Debouncing variables
gesture_start_time = None
last_gesture       = None
triggered          = False
gestures_enabled   = True

tracker    = HandTracker()
controller = MediaController()
cap        = cv2.VideoCapture(0)
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
ser.set_low_latency_mode(True)
time.sleep(2)

def build_frame_bytes(landmarks):
    landmarks_sorted = sorted(landmarks[:21], key=lambda lm: lm[0])
    wrist_x, wrist_y = landmarks_sorted[0][1], landmarks_sorted[0][2]
    max_dist = max(
        (max(abs(lm[1] - wrist_x), abs(lm[2] - wrist_y))
         for lm in landmarks_sorted),
        default=1
    ) or 1
    frame = bytearray()
    for lm in landmarks_sorted:
        lm_id = lm[0]
        nx = max(0, min(65535, int(((lm[1] - wrist_x) / max_dist + 1) * 32767)))
        ny = max(0, min(65535, int(((lm[2] - wrist_y) / max_dist + 1) * 32767)))
        frame.append(lm_id & 0x1F)
        frame.append((nx >> 8) & 0xFF)
        frame.append(nx & 0xFF)
        frame.append((ny >> 8) & 0xFF)
        frame.append(ny & 0xFF)
    return frame

ser.reset_input_buffer()
ser.reset_output_buffer()

frame_count  = 0
no_ack_count = 0

while True:
    success, img = cap.read()
    img = cv2.flip(img, 1)
    if not success:
        break

    img = tracker.find_hands(img, draw=True)
    landmarks, hand_label = tracker.get_landmarks(img)

    if len(landmarks) >= 21:
        payload = build_frame_bytes(landmarks)

        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()
        frame_count += 1

        ack = ser.read(1)
        if len(ack) == 1:
            gesture_id      = ack[0] & 0x07
            current_gesture = GESTURE_NAMES.get(gesture_id, f"ID={gesture_id}")

            # 1. TOGGLE LOGIC (Always Active)
            if current_gesture == 'index_pointing':
                if current_gesture != last_gesture:
                    gesture_start_time = time.time()
                    triggered          = False
                    last_gesture       = current_gesture

                hold_duration = time.time() - gesture_start_time

                if hold_duration > GESTURE_HOLD_TIME and not triggered:
                    gestures_enabled = not gestures_enabled
                    triggered        = True
                    if DEBUG: print(f"System Enabled: {gestures_enabled}")

            # 2. NORMAL GESTURES (Only if Enabled)
            elif gestures_enabled:
                if 'pinch_' in current_gesture:
                    controller.execute_command(current_gesture)
                    triggered    = True
                    last_gesture = current_gesture
                    if DEBUG: print(f"Pinch movement Detected: {current_gesture}")

                elif current_gesture == last_gesture and current_gesture != 'unknown':
                    hold_duration = time.time() - gesture_start_time
                    if hold_duration > GESTURE_HOLD_TIME and not triggered:
                        controller.execute_command(current_gesture)
                        triggered = True
                        if DEBUG: print(f"Held Gesture Executed: {current_gesture}")

                elif current_gesture != last_gesture:
                    last_gesture       = current_gesture
                    gesture_start_time = time.time()
                    triggered          = False

            else:
                last_gesture = None
                triggered    = False

            # 3. UI OVERLAY
            if not gestures_enabled:
                cv2.putText(img, "SYSTEM DISABLED", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                progress_label = "Hold Index to Enable"
            else:
                color = (0, 255, 0) if current_gesture != 'unknown' else (0, 165, 255)
                cv2.putText(img, f"Gesture: {current_gesture}",
                            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
                progress_label = "Hold..."

            if gesture_start_time and current_gesture != 'unknown':
                hold_time   = time.time() - gesture_start_time
                target_time = 2.0 if current_gesture == 'index_pointing' else GESTURE_HOLD_TIME
                progress    = min(hold_time / target_time, 1.0)
                bar_width   = 200
                bar_height  = 20
                filled      = int(bar_width * progress)
                cv2.rectangle(img, (10, 90), (10 + bar_width, 90 + bar_height), (50, 50, 50), -1)
                cv2.rectangle(img, (10, 90), (10 + filled, 90 + bar_height), (0, 255, 0), -1)
                cv2.putText(img, progress_label, (10, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            no_ack_count = 0

        else:
            no_ack_count += 1
            if DEBUG: print(f"[Frame {frame_count}] WARNING: No ACK (timeout #{no_ack_count})")
            if no_ack_count >= 3:
                if DEBUG: print("[RESYNC] Flushing and re-syncing...")
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                no_ack_count = 0
                time.sleep(0.1)

    else:
        # Hand left the frame — reset all gesture state
        gesture_start_time = None
        last_gesture       = None
        triggered          = False

        # Show no-hand indicator
        cv2.putText(img, "No Hand Detected", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (128, 128, 128), 3)

    cv2.imshow("Hand Tracker", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
ser.close()
cv2.destroyAllWindows()