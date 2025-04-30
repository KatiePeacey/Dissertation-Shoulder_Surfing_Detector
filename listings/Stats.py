import cv2
import os
import time
import threading
import tkinter as tk
import customtkinter
from PIL import Image, ImageTk
from playsound import playsound
import csv
from datetime import datetime
import dlib

# Global state
videoCap = cv2.VideoCapture(0)
running = False
dimmed = False
log_file = "detection_log.csv"
alert_sound = "warning.mp3"

# Initialize log file
with open(log_file, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Timestamp", "Event"])

print("Camera ON")

# Utility function
def midpoint(p1, p2):
    return int((p1.x + p2.x) / 2), int((p1.y + p2.y) / 2)

def log_event(event):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, event])

def reset_brightness():
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(100)
    except ImportError:
        os.system("brightness 1.0")


# GUI and Detection Class
class Window(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title("Shoulder Surfing & Gaze Detector")
        self.geometry("1430x768")

        # Sidebar UI
        self.sidebar_frame = customtkinter.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.sidebar_frame.grid_rowconfigure(11, weight=1)

        self.logo_label = customtkinter.CTkLabel(self.sidebar_frame, text="System Settings", font=customtkinter.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.sidebar_button_start = customtkinter.CTkButton(self.sidebar_frame, text="Start Detection", command=self.start_detection)
        self.sidebar_button_start.grid(row=1, column=0, padx=20, pady=10)

        self.sidebar_button_stop = customtkinter.CTkButton(self.sidebar_frame, text="Stop Detection", command=self.stop_detection, state=tk.DISABLED)
        self.sidebar_button_stop.grid(row=2, column=0, padx=20, pady=10)

        self.log_display = customtkinter.CTkTextbox(self.sidebar_frame, height=180, width=180)
        self.log_display.grid(row=3, column=0, padx=10, pady=10)

        self.settings_label = customtkinter.CTkLabel(self.sidebar_frame, text="Settings", font=customtkinter.CTkFont(size=16, weight="bold"))
        self.settings_label.grid(row=4, column=0, pady=(10, 0))

        self.brightness_label = customtkinter.CTkLabel(self.sidebar_frame, text="Dim Level (%)")
        self.brightness_label.grid(row=5, column=0, sticky="sw", padx=20)
        self.brightness_slider = customtkinter.CTkSlider(self.sidebar_frame, from_=0, to=100, number_of_steps=20)
        self.brightness_slider.set(10)
        self.brightness_slider.grid(row=6, column=0, padx=20, pady=5)

        self.threshold_label = customtkinter.CTkLabel(self.sidebar_frame, text="Detection Threshold")
        self.threshold_label.grid(row=7, column=0, sticky="sw", padx=20)
        self.threshold_slider = customtkinter.CTkSlider(self.sidebar_frame, from_=0.1, to=1.0, number_of_steps=9)
        self.threshold_slider.set(0.4)
        self.threshold_slider.grid(row=8, column=0, padx=20, pady=5)

        self.sound_switch = customtkinter.CTkSwitch(self.sidebar_frame, text="Sound Alerts", command=self.toggle_sound)
        self.sound_switch.select()
        self.sound_switch.grid(row=9, column=0, padx=20, pady=5)

        self.apply_button = customtkinter.CTkButton(self.sidebar_frame, text="Apply Settings", command=self.apply_settings)
        self.apply_button.grid(row=10, column=0, padx=20, pady=10)

        # Video Display
        self.video_label = tk.Label(self)
        self.video_label.grid(row=0, column=1, padx=10, pady=10)

        # Default settings
        self.dim_level = 10
        self.detection_threshold = 0.4
        self.sound_enabled = True

        self.auto_refresh_log()

    def update_log_display(self):
        self.log_display.delete("1.0", tk.END)
        self.log_display.insert(tk.END, "🔍 Recent Events:\n----------------------\n")

        try:
            with open(log_file, mode='r') as file:
                reader = csv.reader(file)
                lines = list(reader)[1:][-5:]  # Skip header
                for row in lines:
                    if len(row) >= 2:
                        timestamp, event = row
                        tag = "normal"
                        if "Threat Detected" in event:
                            tag = "threat"
                        self.log_display.insert(tk.END, f"{timestamp} - {event}\n", tag)

                self.log_display.tag_config("normal", foreground="white")
                self.log_display.tag_config("threat", foreground="red")
        except Exception as e:
            self.log_display.insert(tk.END, f"Error reading log: {str(e)}\n")

    def auto_refresh_log(self):
        self.update_log_display()
        self.after(5000, self.auto_refresh_log)

    def apply_settings(self):
        self.dim_level = int(self.brightness_slider.get())
        self.detection_threshold = round(self.threshold_slider.get(), 2)
        self.log_display.insert(tk.END, f"\n⚙️ Settings updated:\n• Dim: {self.dim_level}%\n• Threshold: {self.detection_threshold}\n")
        self.update_log_display()

    def toggle_sound(self):
        self.sound_enabled = self.sound_switch.get()

    def start_detection(self):
        global running
        running = True
        self.apply_settings()
        log_event("Detection Started")
        self.sidebar_button_start.configure(state=tk.DISABLED)
        self.sidebar_button_stop.configure(state=tk.NORMAL)
        detection_thread = threading.Thread(target=self.run_detection)
        detection_thread.start()

    def stop_detection(self):
        global running
        running = False
        reset_brightness()
        log_event("Detection Stopped")
        self.sidebar_button_start.configure(state=tk.NORMAL)
        self.sidebar_button_stop.configure(state=tk.DISABLED)

    def dim_screen(self):
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(self.dim_level)
        except ImportError:
            os.system(f"brightness {self.dim_level / 100:.2f}")

    def show_frame(self, frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.config(image=imgtk)

    def run_detection(self):
        global dimmed

        detector = dlib.get_frontal_face_detector()
        predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

        safe_frame_counter = 0
        THRESHOLD_SAFE_FRAMES = 10

        while running:
            ret, frame = videoCap.read()
            if not ret:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector(gray)

            person_count = len(faces)
            gaze_detected = False

            for face in faces:
                landmarks = predictor(gray, face)

                left_point_left = (landmarks.part(36).x, landmarks.part(36).y)
                right_point_left = (landmarks.part(39).x, landmarks.part(39).y)
                center_top_left = midpoint(landmarks.part(37), landmarks.part(38))
                center_bottom_left = midpoint(landmarks.part(41), landmarks.part(40))

                cv2.line(frame, left_point_left, right_point_left, (0, 255, 0), 2)
                cv2.line(frame, center_top_left, center_bottom_left, (0, 255, 0), 2)

                left_point_right = (landmarks.part(42).x, landmarks.part(42).y)
                right_point_right = (landmarks.part(45).x, landmarks.part(45).y)
                center_top_right = midpoint(landmarks.part(43), landmarks.part(44))
                center_bottom_right = midpoint(landmarks.part(47), landmarks.part(46))

                cv2.line(frame, left_point_right, right_point_right, (0, 255, 0), 2)
                cv2.line(frame, center_top_right, center_bottom_right, (0, 255, 0), 2)

                gaze_detected = True  # Simplified placeholder

            if person_count > 1 and gaze_detected:
                safe_frame_counter = 0  # reset the safe counter

                if not dimmed:
                    print("Potential shoulder surfer detected! Dimming screen")
                    log_event("Threat Detected - Screen Dimmed")
                    self.dim_screen()
                    if self.sound_enabled:
                        playsound(alert_sound)
                    dimmed = True
            else:
                if dimmed:
                    safe_frame_counter += 1
                    if safe_frame_counter >= THRESHOLD_SAFE_FRAMES:
                        print("No threat detected. Restoring brightness.")
                        log_event("No Threat - Brightness Restored")
                        reset_brightness()
                        dimmed = False

            self.show_frame(frame)

            if cv2.waitKey(1) == 27:
                break

if __name__ == "__main__":
    window = Window()
    window.mainloop()

    videoCap.release()
    print("Camera OFF")
    cv2.destroyAllWindows()
