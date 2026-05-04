"""
This module launches the system controller which exexutes the camera feed and starts tracking
It also handles the system disable/enable and debouncing of static gestures based on gesture hold time
"""

import cv2
import time
from hand_tracker import HandTracker
from gesture_recogniser import GestureRecogniser
from media_controller import MediaController
from config import GESTURE_HOLD_TIME, DEBUG

# Setup
tracker = HandTracker()
controller = MediaController()
recon = GestureRecogniser()
cap = cv2.VideoCapture(0)

# Debouncing variables
gesture_start_time = None
last_gesture = None
triggered = False

# Enable/Disable system variable
gestures_enabled = True 

print("Gesture Media Controller Started!")
print("Show gestures to control VLC")

# Debug helper function
def draw_debug_overlay(frame, recon):
    h, w, _ = frame.shape
    
    history = list(recon.swipe_history)
    if len(history) > 1:
        for i in range(len(history) - 1):
            pt1 = (int(history[i][0]), int(history[i][1]))
            pt2 = (int(history[i+1][0]), int(history[i+1][1]))
            cv2.line(frame, pt1, pt2, (0, 255, 255), 2) 

    cv2.rectangle(frame, (w - 220, 0), (w, 120), (0, 0, 0), -1)
    
    cv2.putText(frame, f"Rot Accum: {recon.rotation_accumulator:.1f}", (w - 210, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    cv2.putText(frame, f"Swipe Buffer: {len(recon.swipe_history)}", (w - 210, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    
    lock_status = recon.locked_hand_type if recon.locked_hand_type else "None"
    color = (0, 255, 0) if recon.locked_hand_type else (0, 0, 255)
    cv2.putText(frame, f"Lock: {lock_status}", (w - 210, 90), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

while True:
    success, frame = cap.read()
    if not success: break
    
    frame = cv2.flip(frame, 1)  

    frame = tracker.find_hands(frame)
    landmarks, hand_label = tracker.get_landmarks(frame)

    if landmarks:
        current_gesture = recon.recognise_gesture(landmarks, hand_label, frame)
        
        # 1. TOGGLE LOGIC (Always Active)
        if current_gesture == 'index_pointing':
            if current_gesture != last_gesture:
                gesture_start_time = time.time()
                triggered = False
                last_gesture = current_gesture 
            
            hold_duration = time.time() - gesture_start_time
            
            # DELIBERATE TOGGLE: 
            if hold_duration > 2.0 and not triggered:
                gestures_enabled = not gestures_enabled
                triggered = True
                if DEBUG: print(f"System Enabled: {gestures_enabled}")
                
        # 2. NORMAL GESTURES (Only if Enabled)
        elif gestures_enabled:
            # Dynamic gestures have instant execution
            if 'swipe' in current_gesture:
                controller.execute_command(current_gesture)
                triggered = True
                last_gesture = current_gesture
                if DEBUG: print(f"Swipe Detected: {current_gesture}")

            elif 'fist_move_' in current_gesture:
                controller.execute_command(current_gesture)
                triggered = True
                last_gesture = current_gesture
                if DEBUG: print(f"Fist Movement: {current_gesture}")

            elif 'pinch_' in current_gesture:
                controller.execute_command(current_gesture)
                triggered = True
                last_gesture = current_gesture
                if DEBUG: print(f"Pinch movement Detected: {current_gesture}")

            # Static gestures have to wait for hold time to prevent repeated executions
            elif current_gesture == last_gesture and current_gesture != 'unknown':
                hold_duration = time.time() - gesture_start_time
                if hold_duration > GESTURE_HOLD_TIME and not triggered:
                    controller.execute_command(current_gesture)
                    triggered = True
                    if DEBUG: print(f"Held Gesture Executed: {current_gesture}")
            
            elif current_gesture != last_gesture:
                last_gesture = current_gesture
                gesture_start_time = time.time()
                triggered = False
        
        else:
            last_gesture = None
            triggered = False
        
        # 3. UI OVERLAY LOGIC
        if not gestures_enabled:
            cv2.putText(frame, "SYSTEM DISABLED", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            progress_label = "Hold Index to Enable"
        else:
            color = (0, 255, 0) if current_gesture != 'unknown' else (0, 165, 255)
            cv2.putText(frame, f"Gesture: {current_gesture}", 
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
            progress_label = "Hold..."
        
        # Draw Progress Bar
        if gesture_start_time and current_gesture != 'unknown':
            hold_time = time.time() - gesture_start_time
            
            target_time = 2.0 if current_gesture == 'index_pointing' else GESTURE_HOLD_TIME
            progress = min(hold_time / target_time, 1.0)
            
            bar_width = 200
            bar_height = 20
            filled = int(bar_width * progress)
            
            cv2.rectangle(frame, (10, 90), (10 + bar_width, 90 + bar_height), (50, 50, 50), -1)
            cv2.rectangle(frame, (10, 90), (10 + filled, 90 + bar_height), (0, 255, 0), -1)
            cv2.putText(frame, progress_label, (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
    else:
        last_gesture = None
        triggered = False
    
    if DEBUG: draw_debug_overlay(frame, recon)

    cv2.imshow("Gesture Media Controller", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()