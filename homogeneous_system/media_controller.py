"""
This module uses pynput and the mapping stored in config to execute the keyboard presses
whenever the execution command is sent after detection of the gesture
"""
import os
from pynput.keyboard import Controller, Key
from config import GESTURE_COMMANDS, VLC_KEYS

class MediaController:
    def __init__(self):
        self.keyboard = Controller()
    
    def execute_command(self, gesture):
        command = None
        
        # 1. Check if it's the custom user gesture
        if gesture == 'custom_gesture':
            if os.path.exists("custom_mapping.txt"):
                with open("custom_mapping.txt", "r") as f:
                    command = f.read().strip()
            else:
                command = 'play_pause' # Fallback default
                
        # 2. Otherwise, check standard geometric gestures
        elif gesture in GESTURE_COMMANDS:
            command = GESTURE_COMMANDS[gesture]

        # 3. Execute the mapped key
        if command and command in VLC_KEYS:
            key_combo = VLC_KEYS[command]
            
            # Handle special keys
            if key_combo == 'space':
                self.keyboard.press(Key.space)
                self.keyboard.release(Key.space)

            elif '+' in key_combo:
                parts = key_combo.split('+')
                modifier = parts[0].strip()
                main_key = parts[1].strip()
                
                # Press modifier
                if modifier == 'shift': self.keyboard.press(Key.shift)
                elif modifier == 'ctrl': self.keyboard.press(Key.ctrl)
                elif modifier == 'alt': self.keyboard.press(Key.alt)
                
                # Press main key
                if main_key == 'right':
                    self.keyboard.press(Key.right)
                    self.keyboard.release(Key.right)
                elif main_key == 'left':
                    self.keyboard.press(Key.left)
                    self.keyboard.release(Key.left)
                elif main_key == 'up':
                    self.keyboard.press(Key.up)
                    self.keyboard.release(Key.up)
                elif main_key == 'down':
                    self.keyboard.press(Key.down)
                    self.keyboard.release(Key.down)
                else:
                    self.keyboard.press(main_key)
                    self.keyboard.release(main_key)
                
                # Release modifier
                if modifier == 'shift': self.keyboard.release(Key.shift)
                elif modifier == 'ctrl': self.keyboard.release(Key.ctrl)
                elif modifier == 'alt': self.keyboard.release(Key.alt)
            
            # Regular keys
            else:
                self.keyboard.press(key_combo)
                self.keyboard.release(key_combo)