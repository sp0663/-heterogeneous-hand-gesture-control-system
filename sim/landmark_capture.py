import cv2
import serial
import time
from hand_tracker import HandTracker

SERIAL_PORT = "COM7"        # change to your port e.g. "/dev/ttyUSB0" on Linux
BAUD_RATE = 115200
ACK_TIMEOUT = 0.1          # seconds to wait for gesture ID back

tracker = HandTracker()
cap = cv2.VideoCapture(0)

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout = ACK_TIMEOUT)
time.sleep(2)  # let FPGA/USB-UART settle after port open

def build_frame_bytes(landmarks):
    """
    For each of 21 landmarks: [id (1 byte), x_high, x_low, y_high, y_low]
    Total: 21 * 5 = 105 bytes per frame
    """
    frame = bytearray()
    wrist_x, wrist_y = landmarks[0][1], landmarks[0][2]
    max_dist = max(
        (max(abs(lm[1] - wrist_x), abs(lm[2] - wrist_y)) for lm in landmarks),
        default=1
    ) or 1

    for lm in landmarks[:21]:
        lm_id = lm[0]  # 0-20
        nx = max(0, min(65535, int(((lm[1] - wrist_x) / max_dist + 1) * 32767)))
        ny = max(0, min(65535, int(((lm[2] - wrist_y) / max_dist + 1) * 32767)))

        frame.append(lm_id & 0xFF)           # ID: 1 byte
        frame.append((nx >> 8) & 0xFF)       # X high byte
        frame.append(nx & 0xFF)              # X low byte
        frame.append((ny >> 8) & 0xFF)       # Y high byte
        frame.append(ny & 0xFF)              # Y low byte

    return frame  # 105 bytes total

while True:
    success, frame = cap.read()
    if not success:
        break

    frame = tracker.find_hands(frame, draw=True)
    landmarks, hand_label = tracker.get_landmarks(frame)

    if len(landmarks) > 0:
        payload = build_frame_bytes(landmarks)

        # Send all 105 bytes
        ser.write(payload)
        ser.flush()

        # Wait for gesture ID back from FPGA (ACK)
        ack = ser.read(1)
        if len(ack) == 1:
            gesture_id = ack[0]
            print(f"Gesture ID from FPGA: {gesture_id}")
        else:
            print("WARNING: No ACK received (timeout), FPGA may be busy or lost sync")

    cv2.imshow("Hand Tracker", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
ser.close()
cv2.destroyAllWindows()