"""
This module handles the gesture-to-command mapping and the command-to-keys mapping
It also includes threshold and cooldown variables for the gestures 
"""

# Gesture to VLC command mapping
GESTURE_COMMANDS = {
    # Standard Gestures
    'fist': 'mute',
    'open_palm': 'play_pause',
    'pinch': 'full_screen',
    'swipe_right': 'move_next',
    'swipe_left': 'move_prev',
    'fist_move_up': 'volume_up',      
    'fist_move_down': 'volume_down',  
    'pinch_clockwise': 'jump_forward',
    'pinch_anticlockwise': 'jump_backward',

    # Custom ML Gestures
    # Will be populated automatically by app_ui.py
}

# Comprehensive VLC keyboard shortcuts mapping
VLC_KEYS = {
    'play_pause': 'space',
    'stop': 's',
    'full_screen': 'f',
    'mute': 'm',
    'volume_up': 'ctrl+up',
    'volume_down': 'ctrl+down',
    'move_next': 'n',
    'move_prev': 'p',
    'toggle_loop': 'l',
    'toggle_random': 'r',
    'jump_forward': 'alt+right',
    'jump_backward': 'alt+left',
    'jump_forward_long': 'ctrl+right',
    'jump_backward_long': 'ctrl+left',
    'speed_up': ']',
    'slow_down': '[',
    'normal_speed': '=',
    'next_subtitle': 'v',
    'next_audio_track': 'b',
    'take_snapshot': 'shift+s',
    'show_time': 't',
    'quit_vlc': 'ctrl+q'
}

# Gesture recognition settings
GESTURE_HOLD_TIME = 0.5  
ACCUMULATION_THRESHOLD = 10.0
SWIPE_COOLDOWN = 1
SWIPE_THRESHOLD = 200
FIST_THRESHOLD = 30 

# Hand tracking settings
MAX_HANDS = 1
DETECTION_CONFIDENCE = 0.5
TRACKING_CONFIDENCE = 0.5

# Performance settings
TARGET_FPS = 15
MAX_LATENCY_MS = 200

# Debug mode
DEBUG = True
GESTURE_COMMANDS['peace'] = 'take_snapshot'
