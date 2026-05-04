"""
This module uses the MediaPipe library to track and acquire hand landmarks and hand label
"""

import cv2
import mediapipe as mp

class HandTracker:
    def __init__(self, mode=False, max_hands=1, detection_con=0.5, track_con=0.5):
        self.mode = mode
        self.max_hands = max_hands
        self.detection_con = detection_con
        self.track_con = track_con
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=self.mode,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.detection_con,
            min_tracking_confidence=self.track_con
        )
        
        self.mp_draw = mp.solutions.drawing_utils
        self.results = None

    # Preprocessing and tracking hand using MediaPipe and OpenCV
    def find_hands(self, frame, draw=True):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.hands.process(rgb_frame)

        if self.results.multi_hand_landmarks:
            for hand_landmarks in self.results.multi_hand_landmarks:
                if draw:
                    self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)

        return frame
    
    # Acquires the landmark coordinates and hand label (left or right)
    def get_landmarks(self, frame, hand_no = 0):
        landmark_list = []
        hand_label = None
        
        if self.results.multi_hand_landmarks:
            my_hand = self.results.multi_hand_landmarks[hand_no]
            
            # Get hand label (Left or Right)
            if self.results.multi_handedness:
                hand_label = self.results.multi_handedness[hand_no].classification[0].label
            
            h, w, c = frame.shape
            
            for id, landmark in enumerate(my_hand.landmark):
                cx, cy = int(landmark.x * w), int(landmark.y * h)
                landmark_list.append([id, cx, cy])
        
        return landmark_list, hand_label
