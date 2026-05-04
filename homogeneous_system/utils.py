"""
This module has helper functions which are used in rule based detection
"""

import numpy as np

def cal_distance(point1, point2):
    p1 = np.array([point1[1], point1[2]])
    p2 = np.array([point2[1], point2[2]])
    return np.linalg.norm(p1 - p2)

def cal_angle(point1, point2, point3):
    p1 = np.array([point1[1], point1[2]])
    p2 = np.array([point2[1], point2[2]])
    p3 = np.array([point3[1], point3[2]])

    v1 = p1 - p2
    v2 = p3 - p2

    cosine = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
    cosine = np.clip(cosine, -1.0, 1.0)
    return np.degrees(np.arccos(cosine))

def finger_extended(landmarks, finger_tip_id):
    if finger_tip_id == 4:
        mcp, ip, tip = landmarks[finger_tip_id - 2], landmarks[finger_tip_id - 1], landmarks[finger_tip_id]
        angle1 = cal_angle(mcp, ip, tip)
    else:
        mcp, pcp, dip = landmarks[finger_tip_id - 3], landmarks[finger_tip_id - 2], landmarks[finger_tip_id - 1]
        angle1 = cal_angle(mcp, pcp, dip)
    return (angle1 > 160)
    
def count_extended_fingers(landmarks):
    count = 0
    finger_tip_id = [4, 8, 12, 16, 20]
    for id in finger_tip_id:
        if finger_extended(landmarks, id):
            count += 1
    return count

def is_pinch(landmarks):
    pinch_distance = cal_distance(landmarks[4], landmarks[8])  
    hand_size = cal_distance(landmarks[0], landmarks[9])      
    pinch_ratio = pinch_distance / hand_size
    threshold = 0.25
    return pinch_ratio < threshold

def cntr_pt(landmarks):
    thumb_pt = np.array(landmarks[4][1:])
    index_pt = np.array(landmarks[8][1:])
    cntr_pt = (thumb_pt + index_pt) / 2
    return cntr_pt

def is_index_pointing(landmarks):
    if count_extended_fingers(landmarks) == 1 and finger_extended(landmarks, 8):
        return True
    return False