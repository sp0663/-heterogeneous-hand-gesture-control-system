"""
This module recognises all the static, dynamic and custom gestures based on various rule based logic 
and ML model for the custom gestures. It also handles the timing cooldown for dynamic gestures 
"""

from utils import count_extended_fingers, is_pinch, cal_distance, is_index_pointing
from collections import deque
import time
import math
import pickle
import os
from config import ACCUMULATION_THRESHOLD, SWIPE_COOLDOWN, SWIPE_THRESHOLD, FIST_THRESHOLD

class GestureRecogniser:
    def __init__(self, buffer_size=10):
        # Swipe Variables
        self.swipe_history = deque(maxlen=buffer_size)    
        self.last_swipe_time = 0

        # Pinch Variables    
        self.rotation_accumulator = 0.0     
        self.prev_angle = None      
        self.locked_hand_type = None    
        
        # Fist Variables
        self.last_fist_move_time = 0
        self.vertical_accumulator = 0.0
        self.prev_fist_y = None
        
        # Load the custom ML model if it exists
        self.custom_model = None
        if os.path.exists("gesture_model.pkl"):
            try:
                with open("gesture_model.pkl", "rb") as f:
                    self.custom_model = pickle.load(f)
            except Exception as e:
                pass
    
    def recognise_gesture(self, landmarks, hand_label, frame):
        current_time = time.time()
        count = count_extended_fingers(landmarks)
        current_hand_type = hand_label if hand_label else "Right"
        
        # 1. VELOCITY GATE
        curr_x, curr_y = landmarks[0][1], landmarks[0][2]
        velocity = 0
        if len(self.swipe_history) > 0:
            prev_x, prev_y = self.swipe_history[-1]
            velocity = math.hypot(curr_x - prev_x, curr_y - prev_y)
        self.swipe_history.append((curr_x, curr_y))
        is_moving = velocity > 20

        # 2. SWIPES 
        if count == 5 and (current_time - self.last_swipe_time) > SWIPE_COOLDOWN:
            if len(self.swipe_history) == self.swipe_history.maxlen:
                start_x = self.swipe_history[0][0]
                total_dx = curr_x - start_x
                if abs(total_dx) > SWIPE_THRESHOLD:
                    self.last_swipe_time = current_time
                    self.swipe_history.clear() 
                    return 'swipe_right' if total_dx > 0 else 'swipe_left'

        # STATIC BLOCKER
        if is_moving: return 'unknown'

        # 3. INDEX POINTING (System Toggle - High Priority)
        if is_index_pointing(landmarks):
            # Reset fist tracking variables so it doesn't glitch when transitioning
            self.prev_fist_y = None 
            self.vertical_accumulator = 0
            return 'index_pointing'

        # 4. FIST & DYNAMIC FIST MOVEMENT
        index_folded = landmarks[8][2] > landmarks[5][2] 
        middle_folded = landmarks[12][2] > landmarks[9][2] 
        ring_folded = landmarks[16][2] > landmarks[13][2]
        is_fist_state = (count == 0 or (index_folded and middle_folded and ring_folded))
        
        if is_fist_state:
            current_y = landmarks[0][2] # Wrist Y
            
            if self.prev_fist_y is not None:
                delta_y = current_y - self.prev_fist_y
                
                if abs(delta_y) > 2.0:  
                    self.vertical_accumulator += delta_y
                    self.last_fist_move_time = current_time
                    
                    if self.vertical_accumulator < -FIST_THRESHOLD: 
                        self.vertical_accumulator = 0
                        self.prev_fist_y = current_y 
                        return 'fist_move_up'
                    elif self.vertical_accumulator > FIST_THRESHOLD: 
                        self.vertical_accumulator = 0
                        self.prev_fist_y = current_y
                        return 'fist_move_down'
            
            self.prev_fist_y = current_y
            
            if (current_time - self.last_fist_move_time) > 0.3:
                return 'fist'
            return 'unknown'
        else:
            self.prev_fist_y = None
            self.vertical_accumulator = 0

        # 5. PINCH LOGIC 
        if is_pinch(landmarks):
            pinch_cx = (landmarks[4][1] + landmarks[8][1]) / 2
            pinch_cy = (landmarks[4][2] + landmarks[8][2]) / 2
            dx = pinch_cx - landmarks[0][1]
            dy = pinch_cy - landmarks[0][2]
            current_angle = math.degrees(math.atan2(dy, dx))
            
            delta = 0
            if self.prev_angle is not None:
                delta = current_angle - self.prev_angle
                if delta > 180: delta -= 360
                elif delta < -180: delta += 360
            else:
                self.prev_angle = current_angle
                self.locked_hand_type = current_hand_type
                return 'unknown' 

            self.prev_angle = current_angle
            abs_delta = abs(delta)

            if abs_delta > 1.5:
                if self.locked_hand_type == "Left": effective_delta = -delta 
                else: effective_delta = delta  
                
                self.rotation_accumulator += effective_delta
                
                if self.rotation_accumulator > ACCUMULATION_THRESHOLD:
                    self.rotation_accumulator -= ACCUMULATION_THRESHOLD
                    return 'pinch_clockwise'
                elif self.rotation_accumulator < -ACCUMULATION_THRESHOLD:
                    self.rotation_accumulator += ACCUMULATION_THRESHOLD
                    return 'pinch_anticlockwise'
                
                return 'unknown' 
            elif abs_delta > 1.0:
                return 'unknown'
            else:
                return 'pinch'
        else:
            self.prev_angle = None
            self.locked_hand_type = None

        # 6. OPEN PALM
        wrist_y = landmarks[0][2]
        knuckle_y = landmarks[9][2]
        hand_size = cal_distance(landmarks[0], landmarks[9]) or 1
        vertical_ratio = (wrist_y - knuckle_y) / hand_size
        
        if count == 5 and vertical_ratio > 0.5:
            return 'open_palm'
            
        # 7. CUSTOM ML GESTURE
        if self.custom_model:
            wrist_x = landmarks[0][1]
            wrist_y = landmarks[0][2]

            flat_landmarks = []
            for lm in landmarks:
                flat_landmarks.append(lm[1] - wrist_x)
                flat_landmarks.append(lm[2] - wrist_y)
                
            try:
                probabilities = self.custom_model.predict_proba([flat_landmarks])[0]
                classes = self.custom_model.classes_
                max_prob = max(probabilities)
                best_class = classes[list(probabilities).index(max_prob)]
                
                if max_prob > 0.80 and best_class.lower() not in ['background', 'neutral', 'none']:
                    return best_class
            except Exception as e:
                pass 
                
        return 'unknown'