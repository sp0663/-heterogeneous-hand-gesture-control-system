"""
This module executes the system UI which is used to launch the controller or collect samples  new custom gesture using ML model 
and map to new VLC function or delete existing ML model gestures
"""
"""
OPERATING PROCEDURE

    Launch UI: Run python app_ui.py to open the control dashboard and to use the whole system.

    Train (Optional): Close the controller if open, Click 'Train New Gestures' to add custom ML gestures.
    IMPORTANT: Always record a 'background' gesture so the model learns your resting hand state.

    Map: Select a gesture and a VLC action, then click 'Save Mapping'.
    NOTE: You must repeat this save process for every custom gesture you trained.
    you can delete the ml model as a whole with the "delete custom data" button

    Launch: Click 'Launch Controller' to start the camera and control VLC.
    """

import tkinter as tk
from tkinter import messagebox
import os
import subprocess
import sys
import threading
import pickle
import config  

class GestureControllerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gesture Media Controller")
        self.root.geometry("450x520")
        self.root.configure(padx=20, pady=20)
        
        self.controller_process = None

        # HEADER 
        tk.Label(root, text="HCI Media Controller", font=("Arial", 16, "bold")).pack(pady=(0, 5))
        tk.Label(root, text="NVIDIA Jetson Nano Edition", font=("Arial", 10, "italic"), fg="gray").pack(pady=(0, 15))

        # MAIN CONTROLLER SECTION
        self.status_var = tk.StringVar(value="Status: INACTIVE")
        self.status_label = tk.Label(root, textvariable=self.status_var, font=("Arial", 12, "bold"), fg="red")
        self.status_label.pack(pady=(0, 10))

        self.start_btn = tk.Button(root, text="Launch Controller", width=25, height=2, 
                                   bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
                                   command=self.toggle_controller)
        self.start_btn.pack(pady=5)

        tk.Frame(root, height=2, bd=1, relief="sunken").pack(fill="x", pady=15)

        # GESTURE TRAINING
        tk.Label(root, text="1. Train Custom ML Gestures", font=("Arial", 12, "bold")).pack(pady=(0, 5))

        self.train_btn = tk.Button(root, text="Train New Gestures", width=25, 
                                   bg="#2196F3", fg="white", font=("Arial", 10),
                                   command=self.train_gesture)
        self.train_btn.pack(pady=5)
        
        # DELETE BUTTON
        self.delete_btn = tk.Button(root, text="Delete Custom Data", width=25, 
                                    bg="#f44336", fg="white", font=("Arial", 10),
                                    command=self.delete_gesture)
        self.delete_btn.pack(pady=5)
        
        tk.Frame(root, height=2, bd=1, relief="sunken").pack(fill="x", pady=15)

        # DYNAMIC MAPPING SECTION
        tk.Label(root, text="2. Map Gestures to VLC", font=("Arial", 12, "bold")).pack(pady=(0, 5))
        
        mapping_frame = tk.Frame(root)
        mapping_frame.pack(pady=5)
        
        # Gesture Dropdown 
        self.gesture_var = tk.StringVar(value="Select Gesture")
        self.gesture_dropdown = tk.OptionMenu(mapping_frame, self.gesture_var, "Select Gesture")
        self.gesture_dropdown.config(width=15)
        self.gesture_dropdown.grid(row=0, column=0, padx=5)
        
        tk.Label(mapping_frame, text="➔").grid(row=0, column=1)
        
        # Action Dropdown 
        self.action_var = tk.StringVar(value="Select Action")
        self.available_actions = list(config.VLC_KEYS.keys())
        self.action_dropdown = tk.OptionMenu(mapping_frame, self.action_var, *self.available_actions)
        self.action_dropdown.config(width=15)
        self.action_dropdown.grid(row=0, column=2, padx=5)
        
        self.map_btn = tk.Button(root, text="Save Mapping to Config", bg="#FF9800", fg="white", font=("Arial", 10), command=self.save_mapping)
        self.map_btn.pack(pady=10)

        # Load gestures on startup
        self.load_trained_gestures()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_trained_gestures(self):
        # Reads the trained model and populates the UI dropdown dynamically.
        if os.path.exists("gesture_model.pkl"):
            try:
                with open("gesture_model.pkl", "rb") as f:
                    model = pickle.load(f)
                classes = [c for c in model.classes_ if c.lower() not in ['background', 'neutral', 'none']]
                
                if classes:
                    menu = self.gesture_dropdown["menu"]
                    menu.delete(0, "end")
                    for c in classes:
                        menu.add_command(label=c, command=lambda value=c: self.gesture_var.set(value))
                    self.gesture_var.set(classes[0])
            except Exception as e:
                print(f"Could not load model classes: {e}")

    def save_mapping(self):
        # Updates the config file for new custom gesture
        gesture = self.gesture_var.get()
        action = self.action_var.get()
        
        if gesture == "Select Gesture" or action == "Select Action":
            messagebox.showwarning("Error", "Please select both a gesture and an action.")
            return
            
        try:
            with open("config.py", "r") as f:
                lines = f.readlines()
            
            lines = [line for line in lines if not line.startswith(f"GESTURE_COMMANDS['{gesture}']")]
            lines.append(f"\nGESTURE_COMMANDS['{gesture}'] = '{action}'\n")
            
            with open("config.py", "w") as f:
                f.writelines(lines)
                
            messagebox.showinfo("Success", f"Successfully mapped '{gesture}' to '{action}'!\nYou can now launch the controller.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update config.py: {e}")

    def toggle_controller(self):
        # Executes the main system controller
        if self.controller_process is None or self.controller_process.poll() is not None:
            print("Launching main.py...")
            self.controller_process = subprocess.Popen([sys.executable, "main.py"])
            self.status_var.set("Status: RUNNING")
            self.status_label.config(fg="green")
            self.start_btn.config(text="Stop Controller", bg="#f44336")
            self.train_btn.config(state="disabled")
            self.delete_btn.config(state="disabled") 
            self.map_btn.config(state="disabled")
        else:
            print("Terminating main.py...")
            self.controller_process.terminate()
            self.controller_process = None
            self.status_var.set("Status: INACTIVE")
            self.status_label.config(fg="red")
            self.start_btn.config(text="Launch Controller", bg="#4CAF50")
            self.train_btn.config(state="normal")
            self.delete_btn.config(state="normal")
            self.map_btn.config(state="normal")

    def train_gesture(self):
        # Executes the sample collection and training model
        messagebox.showinfo("Train Gesture", "Opening data collection script in your terminal. Follow the prompts there.")
        
        def run_training_pipeline():
            self.train_btn.config(state="disabled") 
            self.delete_btn.config(state="disabled")
            try:
                subprocess.run([sys.executable, "collect_gesture_data.py"])
                subprocess.run([sys.executable, "train_model.py"])
                
                self.root.after(0, self.load_trained_gestures)
                self.root.after(0, lambda: messagebox.showinfo("Success", "Custom models updated! Map them below."))
            except Exception as e:
                print(f"Error: {e}")
            finally:
                self.root.after(0, lambda: self.train_btn.config(state="normal"))
                self.root.after(0, lambda: self.delete_btn.config(state="normal"))

        threading.Thread(target=run_training_pipeline, daemon=True).start()

    def delete_gesture(self):
        # Clears the dropdown menu
        files_to_delete = ["gesture_model.pkl", "gesture_data.csv"]
        deleted_any = False
        
        for file in files_to_delete:
            if os.path.exists(file):
                os.remove(file)
                deleted_any = True
                
        if deleted_any:
            # Clear the UI dropdown back to default
            menu = self.gesture_dropdown["menu"]
            menu.delete(0, "end")
            self.gesture_var.set("Select Gesture")
            messagebox.showinfo("Success", "Custom gesture data and ML model deleted.")
        else:
            messagebox.showwarning("Not Found", "No custom gesture data found to delete.")

    def on_closing(self):
        if self.controller_process is not None and self.controller_process.poll() is None:
            self.controller_process.terminate()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = GestureControllerUI(root)
    root.mainloop()
