import cv2
import serial
import time
from hand_tracker import HandTracker

SERIAL_PORT  = "COM8"
BAUD_RATE    = 115200
ACK_TIMEOUT  = 0.5       # 500ms — enough for 105 bytes + pipeline latency

GESTURE_NAMES = {
    0: "PINCH",
    1: "FIST",
    2: "OPEN_HAND",
    3: "INDEX_FINGER",
    4: "UNKNOWN",
    5: "PINCH_CW",
    6: "PINCH_ACW"
}

tracker = HandTracker()
cap     = cv2.VideoCapture(0)
ser     = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=ACK_TIMEOUT)
time.sleep(2)

def build_frame_bytes(landmarks):
    """
    Sort landmarks by ID first to guarantee correct order.
    For each of 21 landmarks: [id, x_high, x_low, y_high, y_low]
    Total: 105 bytes per frame.
    Coordinates normalised relative to wrist, scaled to [0, 65535].
    """
    # Sort by landmark ID to guarantee order 0-20
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

        frame.append(lm_id & 0x1F)        # ID  (5-bit safe)
        frame.append((nx >> 8) & 0xFF)    # X high
        frame.append(nx & 0xFF)           # X low
        frame.append((ny >> 8) & 0xFF)    # Y high
        frame.append(ny & 0xFF)           # Y low

    return frame  # 105 bytes

ser.reset_input_buffer()
ser.reset_output_buffer()

frame_count  = 0
no_ack_count = 0

while True:
    success, img = cap.read()
    if not success:
        break

    img = tracker.find_hands(img, draw=True)
    landmarks, hand_label = tracker.get_landmarks(img)

    if len(landmarks) >= 21:
        payload = build_frame_bytes(landmarks)

        # Flush stale ACK bytes before sending new frame
        ser.reset_input_buffer()

        ser.write(payload)
        ser.flush()
        frame_count += 1

        # Read gesture ID back
        ack = ser.read(1)
        if len(ack) == 1:
            gesture_id   = ack[0] & 0x07
            gesture_name = GESTURE_NAMES.get(gesture_id, f"ID={gesture_id}")
            no_ack_count = 0
            print(f"[Frame {frame_count}] {gesture_name} (raw=0x{ack[0]:02X})")
        else:
            no_ack_count += 1
            print(f"[Frame {frame_count}] WARNING: No ACK (timeout #{no_ack_count})")

            # After 3 misses flush everything and re-sync
            if no_ack_count >= 3:
                print("[RESYNC] Flushing and re-syncing...")
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                no_ack_count = 0
                time.sleep(0.1)

    cv2.imshow("Hand Tracker", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
ser.close()
cv2.destroyAllWindows()