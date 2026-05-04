"""
This module is used to collect the samples for the custom gesture which will be used to train the ML model
"""

import cv2
import numpy as np
import csv
import time
from hand_tracker import HandTracker

def collect_data():
    tracker = HandTracker()
    cap = cv2.VideoCapture(0)

    gestures = []
    print("\n=== CUSTOM GESTURE TRAINER ===")
    print("Type the name of a gesture you want to record (e.g., 'peace_sign').")
    print("IMPORTANT: Always add a 'background' gesture so the model knows your resting state!")
    print("Press ENTER without typing anything when you are done adding gestures.\n")
    
    while True:
        g_name = input(f"Enter name for gesture #{len(gestures) + 1}: ").strip()
        if not g_name:
            if len(gestures) < 2:
                print("You must add at least 2 gestures to train a model!")
                continue
            break
        gestures.append(g_name)

    # Prepare CSV
    with open("gesture_data.csv", "w", newline="") as f:
        writer = csv.writer(f)
        header = ["label"] + [f"val_{i}" for i in range(42)]
        writer.writerow(header)

        # Record each gesture sequentially
        for gesture_name in gestures:
            print(f"\n--- Get ready to record '{gesture_name}' in 3 seconds ---")
            for i in range(3, 0, -1):
                print(f"{i}...")
                time.sleep(1)
                
            print(f"Recording '{gesture_name}'...")
            count = 0
            
            # 300 for robust variance
            target_frames = 300 
            
            while count < target_frames:
                success, frame = cap.read()
                frame = cv2.flip(frame, 1)
                frame = tracker.find_hands(frame)
                landmarks, _ = tracker.get_landmarks(frame)
                
                # VARIANCE WARNING UI
                # Creates a flashing effect every 15 frames
                if count % 30 < 15:
                    cv2.putText(frame, "MOVE & ROTATE HAND SLIGHTLY!", (10, 90), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
                
                if landmarks:
                    # Normalization (Wrist becomes 0,0)
                    wrist_x, wrist_y = landmarks[0][1], landmarks[0][2]
                    flat = []
                    for lm in landmarks:
                        flat.extend([lm[1] - wrist_x, lm[2] - wrist_y])
                    
                    writer.writerow([gesture_name] + flat)
                    count += 1
                    
                    # Progress Tracker
                    cv2.putText(frame, f"Recording {gesture_name}: {count}/{target_frames}", 
                                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    
                    # Progress Bar
                    progress = int((count / target_frames) * 400)
                    cv2.rectangle(frame, (10, 110), (10 + progress, 130), (0, 255, 0), -1)
                    
                else:
                    cv2.putText(frame, "Hand not detected! Keep in frame.", (10, 50), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                cv2.imshow("Data Collection", frame)
                cv2.waitKey(1)

    cap.release()
    cv2.destroyAllWindows()
    print("Data collection complete. Saved to gesture_data.csv")

if __name__ == "__main__":
    collect_data()