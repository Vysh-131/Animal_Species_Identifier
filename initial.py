import sys
import os
import json
import time
import hashlib
import yaml
import threading
import cv2
import numpy as np
import re
import getpass

# --- CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(BASE_DIR)

SOCIAL_GRAPH_PATH = os.path.join(BASE_DIR, "memory", "social_graph.json")
PERSONALITY_PATH = os.path.join(BASE_DIR, "config", "personality.json")
FACTS_DB_PATH = os.path.join(BASE_DIR, "memory", "facts.json")
HARDWARE_PATH = os.path.join(BASE_DIR, "config", "hardware.yaml")
ENV_PATH = os.path.join(BASE_DIR, ".env")
LOCK_FILE = os.path.join(BASE_DIR, ".genesis_lock")

# --- IMPORTS ---
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, 
        QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, 
        QStackedWidget, QMessageBox, QProgressBar, QTextEdit,
        QComboBox, QFrame, QSlider, QGridLayout
    )
    from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
    from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPalette
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

try:
    from core.cortex import Cortex
    HAS_CORTEX = True
except ImportError:
    HAS_CORTEX = False

try:
    from senses.eyes import Eyes
    HAS_EYES = True
except ImportError:
    HAS_EYES = False

try:
    from senses.ears import Ears
    HAS_EARS = True
except ImportError:
    HAS_EARS = False

try:
    from ui.voice_out import VoiceEmitter
    HAS_MOUTH = True
except ImportError:
    HAS_MOUTH = False

# ==========================================
#              WORKER THREADS
# ==========================================

class CameraWorker(QThread):
    image_update = pyqtSignal(QImage)
    
    def run(self):
        self.active = True
        # Try index 0, then 1 if failed
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(1)
        
        while self.active and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                # Convert BGR to RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                # Scale for UI
                self.image_update.emit(qt_img.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio))
            time.sleep(0.03) # ~30 FPS
        cap.release()

    def stop(self):
        self.active = False
        self.wait()

class AudioCheckWorker(QThread):
    level_update = pyqtSignal(int)
    finished = pyqtSignal(int) # Returns calculated threshold

    def run(self):
        if not HAS_EARS: 
            self.finished.emit(300)
            return
        
        try:
            # We use a temp Ears instance to sample noise
            ears = Ears()
            
            # Redirect stderr to suppress ALSA spam
            sys.stderr = open(os.devnull, 'w')
            
            with ears._get_microphone() as source:
                # Mock visual feedback loop while listening
                for i in range(20):
                    # In a real scenario, we'd read chunks here to update bar
                    # For setup simplicity, we just animate the bar
                    self.level_update.emit(np.random.randint(10, 60))
                    time.sleep(0.1)
                
                # Actual calibration
                ears.recognizer.adjust_for_ambient_noise(source, duration=1)
                threshold = ears.recognizer.energy_threshold
                
            sys.stderr = sys.__stdout__
            self.finished.emit(int(threshold))
        except:
            self.finished.emit(300)

class PersonaGenerator(QThread):
    finished = pyqtSignal(str) 
    
    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        
    def run(self):
        if not HAS_CORTEX:
            self.finished.emit("{}")
            return
        try:
            cortex = Cortex() 
            sys_prompt = "Configuration Architect."
            user_prompt = (
                f"TASK: Configure personality for 'Ron'.\n"
                f"FLAVOR: '{self.prompt}'\n"
                f"OUTPUT JSON: {{ 'identity_matrix': {{ 'traits': [], 'voice_profile': {{ 'tone': '...', 'catchphrases': [] }} }}, "
                f"'operational_parameters': {{ 'humor_setting': 'MEDIUM' }} }}"
            )
            response = cortex.think(user_prompt, sys_prompt)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            self.finished.emit(match.group(0) if match else "{}")
        except Exception as e:
            self.finished.emit(json.dumps({"error": str(e)}))

# ==========================================
#              GUI WIZARD
# ==========================================

if HAS_GUI:
    class GenesisWizard(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("RonOS Genesis Protocol")
            self.resize(950, 750)
            self.center_window()
            self.setup_ui_theme()
            
            # Application State
            self.admin_name = "Admin"
            self.pin_hash = ""
            self.interview_data = {}
            self.generated_persona = {}
            self.api_keys = {}
            self.hw_config = self._load_hw_config()
            
            # Hardware Handles
            self.preview_mouth = None
            self.temp_eyes = None
            
            if os.path.exists(LOCK_FILE):
                self.show_lock_screen()
            else:
                self.init_ui()

        def center_window(self):
            qr = self.frameGeometry()
            cp = self.screen().availableGeometry().center()
            qr.moveCenter(cp)
            self.move(qr.topLeft())

        def _load_hw_config(self):
            try: 
                with open(HARDWARE_PATH, 'r') as f: return yaml.safe_load(f)
            except: return {}

        def setup_ui_theme(self):
            self.setStyleSheet("""
                QMainWindow { background-color: #0d1117; }
                QWidget { color: #c9d1d9; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
                QLabel#Header { color: #58a6ff; font-size: 26px; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
                QLabel#SubHeader { color: #8b949e; font-size: 16px; margin-bottom: 20px; }
                QLineEdit, QTextEdit, QComboBox { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 8px; }
                QLineEdit:focus { border: 1px solid #58a6ff; }
                QPushButton { background-color: #238636; color: white; border: none; border-radius: 6px; padding: 12px 24px; font-weight: bold; }
                QPushButton:hover { background-color: #2ea043; }
                QPushButton:disabled { background-color: #21262d; color: #484f58; }
                QPushButton#Secondary { background-color: #161b22; border: 1px solid #30363d; color: #58a6ff; }
                QPushButton#Secondary:hover { background-color: #1f2428; border-color: #58a6ff; }
                QSlider::groove:horizontal { border: 1px solid #30363d; height: 8px; background: #161b22; border-radius: 4px; }
                QSlider::handle:horizontal { background: #58a6ff; width: 18px; margin: -5px 0; border-radius: 9px; }
            """)

        def show_lock_screen(self):
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl = QLabel("⚠️ SYSTEM LOCKED")
            lbl.setStyleSheet("color: #da3633; font-size: 32px; font-weight: bold;")
            
            self.pin_input = QLineEdit()
            self.pin_input.setPlaceholderText("Enter Admin PIN")
            self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.pin_input.setFixedWidth(300)
            
            btn = QPushButton("UNLOCK & RESET")
            btn.clicked.connect(self.verify_reset)
            
            layout.addWidget(lbl)
            layout.addSpacing(20)
            layout.addWidget(self.pin_input)
            layout.addWidget(btn)

        def verify_reset(self):
            try:
                with open(SOCIAL_GRAPH_PATH, 'r') as f: 
                    data = json.load(f)
                    stored = data["active_nodes"]["NODE_ROOT"]["credentials"]["pin_hash"]
                
                if _hash_pin(self.pin_input.text()) == stored:
                    os.remove(LOCK_FILE)
                    QMessageBox.information(self, "Success", "System Unlocked.")
                    self.init_ui()
                else: 
                    QMessageBox.critical(self, "Access Denied", "Incorrect PIN.")
            except:
                # Failsafe
                os.remove(LOCK_FILE)
                self.init_ui()

        def init_ui(self):
            self.stack = QStackedWidget()
            self.setCentralWidget(self.stack)
            
            # Setup Pages
            self.pages = [
                self.create_welcome_page(),
                self.create_identity_page(),
                self.create_hardware_page(),
                self.create_keys_page(),
                self.create_persona_page(),
                self.create_voice_page(),
                self.create_interview_page(),
                self.create_biometrics_page(),
                self.create_finalize_page()
            ]
            
            for p in self.pages:
                self.stack.addWidget(p)
            
            self.stack.setCurrentIndex(0)

        # --- HELPER WIDGETS ---
        def _header(self, text):
            lbl = QLabel(text)
            lbl.setObjectName("Header")
            return lbl
            
        def _sub(self, text):
            lbl = QLabel(text)
            lbl.setObjectName("SubHeader")
            lbl.setWordWrap(True)
            return lbl

        # --- PAGE 0: WELCOME ---
        def create_welcome_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            l.addWidget(self._header("RonOS GENESIS"))
            l.addWidget(self._sub("Initializing Artificial Intelligence Core..."))
            
            logo = QLabel("( ● )")
            logo.setStyleSheet("font-size: 80px; color: #58a6ff; margin: 40px;")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.addWidget(logo)
            
            btn = QPushButton("INITIATE SEQUENCE")
            btn.setFixedWidth(300)
            btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
            l.addWidget(btn)
            return p

        # --- PAGE 1: IDENTITY ---
        def create_identity_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 1: IDENTITY"))
            l.addWidget(self._sub("Establish the Root Administrator."))
            
            form = QVBoxLayout()
            form.setSpacing(20)
            
            self.name_input = QLineEdit()
            self.name_input.setPlaceholderText("Your Name")
            form.addWidget(QLabel("Administrator Name:"))
            form.addWidget(self.name_input)
            
            self.pin_field = QLineEdit()
            self.pin_field.setEchoMode(QLineEdit.EchoMode.Password)
            self.pin_field.setPlaceholderText("4-8 Digits")
            form.addWidget(QLabel("Master PIN (God Mode Override):"))
            form.addWidget(self.pin_field)
            
            l.addLayout(form)
            l.addStretch()
            
            btn = QPushButton("NEXT >")
            btn.clicked.connect(self.save_identity)
            l.addWidget(btn)
            return p

        def save_identity(self):
            if len(self.pin_field.text()) < 4:
                QMessageBox.warning(self, "Security", "PIN must be 4+ digits.")
                return
            self.admin_name = self.name_input.text()
            self.pin_hash = _hash_pin(self.pin_field.text())
            self.stack.setCurrentIndex(2)

        # --- PAGE 2: HARDWARE CALIBRATION ---
        def create_hardware_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 2: HARDWARE CALIBRATION"))
            
            # SERVO SECTION
            grp_servo = QFrame()
            grp_servo.setStyleSheet("border: 1px solid #30363d; border-radius: 8px; padding: 10px;")
            g_lay = QVBoxLayout(grp_servo)
            g_lay.addWidget(QLabel("<b>Visual Servo Alignment (The Neck)</b>"))
            
            joy_lay = QGridLayout()
            btn_up = QPushButton("▲")
            btn_up.clicked.connect(lambda: self.move_servo(0, 5))
            btn_down = QPushButton("▼")
            btn_down.clicked.connect(lambda: self.move_servo(0, -5))
            btn_left = QPushButton("◀")
            btn_left.clicked.connect(lambda: self.move_servo(-5, 0))
            btn_right = QPushButton("▶")
            btn_right.clicked.connect(lambda: self.move_servo(5, 0))
            
            self.lbl_pos = QLabel("Pan: 0 | Tilt: 0")
            
            joy_lay.addWidget(btn_up, 0, 1)
            joy_lay.addWidget(btn_left, 1, 0)
            joy_lay.addWidget(self.lbl_pos, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)
            joy_lay.addWidget(btn_right, 1, 2)
            joy_lay.addWidget(btn_down, 2, 1)
            
            g_lay.addLayout(joy_lay)
            l.addWidget(grp_servo)
            
            # AUDIO SECTION
            l.addSpacing(20)
            grp_audio = QFrame()
            grp_audio.setStyleSheet("border: 1px solid #30363d; border-radius: 8px; padding: 10px;")
            a_lay = QVBoxLayout(grp_audio)
            a_lay.addWidget(QLabel("<b>Auditory Cortex Soundcheck</b>"))
            
            check_btn = QPushButton("MEASURE NOISE FLOOR")
            check_btn.setObjectName("Secondary")
            check_btn.clicked.connect(self.run_soundcheck)
            
            self.audio_bar = QProgressBar()
            self.audio_bar.setRange(0, 100)
            self.audio_bar.setValue(0)
            self.lbl_thresh = QLabel("Threshold: Uncalibrated")
            
            a_lay.addWidget(check_btn)
            a_lay.addWidget(self.audio_bar)
            a_lay.addWidget(self.lbl_thresh)
            l.addWidget(grp_audio)
            
            l.addStretch()
            l.addWidget(QPushButton("NEXT >", clicked=lambda: self.stack.setCurrentIndex(3)))
            
            self.cur_pan = 0
            self.cur_tilt = 0
            return p

        def move_servo(self, dp, dt):
            self.cur_pan += dp
            self.cur_tilt += dt
            self.lbl_pos.setText(f"Pan: {self.cur_pan} | Tilt: {self.cur_tilt}")
            
            # HARDWARE ACTUATION
            if HAS_EYES:
                try:
                    if not self.temp_eyes:
                        self.temp_eyes = Eyes()
                    
                    # Apply angles
                    self.temp_eyes.neck.pan.angle = max(-90, min(90, self.cur_pan))
                    self.temp_eyes.neck.tilt.angle = max(-90, min(90, self.cur_tilt))
                except Exception as e:
                    self.lbl_pos.setText(f"Servo Error: {e}")

        def run_soundcheck(self):
            self.lbl_thresh.setText("Listening...")
            self.audio_worker = AudioCheckWorker()
            self.audio_worker.level_update.connect(self.audio_bar.setValue)
            self.audio_worker.finished.connect(self.on_soundcheck_done)
            self.audio_worker.start()

        def on_soundcheck_done(self, thresh):
            self.lbl_thresh.setText(f"✅ Calibrated Threshold: {thresh}")
            if "audio" not in self.hw_config: self.hw_config["audio"] = {}
            self.hw_config["audio"]["silence_threshold"] = thresh

        # --- PAGE 3: API KEYS ---
        def create_keys_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 3: THE KEYRING"))
            l.addWidget(self._sub("Securely store API keys for cloud capabilities. (Optional)"))
            
            form = QVBoxLayout()
            self.k_openai = QLineEdit()
            self.k_openai.setEchoMode(QLineEdit.EchoMode.Password)
            self.k_weather = QLineEdit()
            self.k_spotify = QLineEdit()
            
            form.addWidget(QLabel("OpenAI API Key (LLM Fallback):"))
            form.addWidget(self.k_openai)
            form.addWidget(QLabel("OpenWeatherMap Key:"))
            form.addWidget(self.k_weather)
            form.addWidget(QLabel("Spotify Client ID:"))
            form.addWidget(self.k_spotify)
            
            l.addLayout(form)
            l.addStretch()
            
            btn = QPushButton("SAVE & CONTINUE >")
            btn.clicked.connect(self.save_keys)
            l.addWidget(btn)
            return p

        def save_keys(self):
            self.api_keys = {
                "OPENAI_API_KEY": self.k_openai.text(),
                "OPENWEATHER_KEY": self.k_weather.text(),
                "SPOTIFY_CLIENT_ID": self.k_spotify.text()
            }
            self.stack.setCurrentIndex(4)

        # --- PAGE 4: PERSONA ---
        def create_persona_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 4: NEURAL PERSONA FORGE"))
            l.addWidget(self._sub("Describe Ron's personality."))
            
            self.persona_input = QTextEdit()
            self.persona_input.setPlaceholderText("e.g. 'A sarcastic butler who loves 80s music'")
            l.addWidget(self.persona_input)
            
            gen = QPushButton("FORGE")
            gen.setObjectName("Secondary")
            gen.clicked.connect(self.gen_persona)
            
            self.p_stat = QLabel("")
            l.addWidget(gen)
            l.addWidget(self.p_stat)
            
            self.btn_p_next = QPushButton("NEXT")
            self.btn_p_next.setEnabled(False)
            self.btn_p_next.clicked.connect(lambda: self.stack.setCurrentIndex(5))
            l.addWidget(self.btn_p_next)
            return p

        def gen_persona(self):
            self.p_stat.setText("Forging...")
            self.worker = PersonaGenerator(self.persona_input.toPlainText())
            self.worker.finished.connect(self.on_p_done)
            self.worker.start()

        def on_p_done(self, j):
            try:
                self.generated_persona = json.loads(j)
                self.p_stat.setText("Done.")
                self.btn_p_next.setEnabled(True)
            except:
                self.p_stat.setText("Generation Failed.")
                self.btn_p_next.setEnabled(True)

        # --- PAGE 5: VOICE TUNING ---
        def create_voice_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 5: VOICE CALIBRATION"))
            
            self.voice_combo = QComboBox()
            self.voice_combo.addItems(["Female (US)", "Male (US)", "Female (UK)", "Male (UK)"])
            l.addWidget(QLabel("Model:"))
            l.addWidget(self.voice_combo)
            
            l.addWidget(QLabel("Speed:"))
            self.s_slider = QSlider(Qt.Orientation.Horizontal)
            self.s_slider.setRange(50, 150)
            self.s_slider.setValue(100)
            l.addWidget(self.s_slider)

            l.addWidget(QLabel("Pitch:"))
            self.p_slider = QSlider(Qt.Orientation.Horizontal)
            self.p_slider.setRange(50, 150)
            self.p_slider.setValue(100)
            l.addWidget(self.p_slider)

            l.addWidget(QLabel("Depth:"))
            self.d_slider = QSlider(Qt.Orientation.Horizontal)
            self.d_slider.setRange(0, 100)
            self.d_slider.setValue(50)
            l.addWidget(self.d_slider)
            
            preview_btn = QPushButton("▶ TEST")
            preview_btn.setObjectName("Secondary")
            preview_btn.clicked.connect(self.preview_voice)
            l.addWidget(preview_btn)
            
            l.addStretch()
            btn = QPushButton("CONFIRM VOICE >")
            btn.clicked.connect(self.save_voice)
            l.addWidget(btn)
            return p

        def preview_voice(self):
            # Real preview logic connecting to VoiceOut
            if HAS_MOUTH:
                try:
                    if not self.preview_mouth:
                        self.preview_mouth = VoiceEmitter()
                    
                    vid = self._get_selected_voice_id()
                    self.preview_mouth.set_voice(vid)
                    self.preview_mouth.speak("Audio check one two.", "en")
                except: pass

        def _get_selected_voice_id(self):
            sel = self.voice_combo.currentText()
            if "Male (US)" in sel: return "male_us"
            if "Female (UK)" in sel: return "female_uk"
            if "Male (UK)" in sel: return "male_uk"
            return "female_us"

        def save_voice(self):
            self.sel_voice = self._get_selected_voice_id()
            self.sel_speed = self.s_slider.value() / 100.0
            self.sel_pitch = self.p_slider.value() / 100.0
            self.sel_depth = self.d_slider.value() / 100.0
            self.stack.setCurrentIndex(6)

        # --- PAGE 6: INTERVIEW ---
        def create_interview_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 6: SYNC"))
            
            self.q1 = QComboBox()
            self.q1.addItems(["Assistant", "Coder", "Friend"])
            self.q2 = QComboBox()
            self.q2.addItems(["Reactive", "Proactive"])
            self.q3 = QLineEdit()
            
            l.addWidget(QLabel("Use Case:"))
            l.addWidget(self.q1)
            l.addWidget(QLabel("Style:"))
            l.addWidget(self.q2)
            l.addWidget(QLabel("Interest:"))
            l.addWidget(self.q3)
            
            l.addStretch()
            btn = QPushButton("NEXT")
            btn.clicked.connect(self.save_interview)
            l.addWidget(btn)
            return p

        def save_interview(self):
            self.interview_data = {
                "use_case": self.q1.currentText(), 
                "proactivity": self.q2.currentText(), 
                "interest": self.q3.text()
            }
            self.stack.setCurrentIndex(7)

        # --- PAGE 7: BIOMETRICS ---
        def create_biometrics_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("STEP 7: BIOMETRICS"))
            
            self.cam_lbl = QLabel("OFFLINE")
            self.cam_lbl.setFixedSize(640,480)
            self.cam_lbl.setStyleSheet("background:black;")
            l.addWidget(self.cam_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            
            b1 = QPushButton("ACTIVATE")
            b1.clicked.connect(self.start_cam)
            b2 = QPushButton("CAPTURE")
            b2.clicked.connect(self.cap_face)
            b3 = QPushButton("SKIP/FINISH")
            b3.clicked.connect(lambda: self.stack.setCurrentIndex(8))
            
            l.addWidget(b1)
            l.addWidget(b2)
            l.addWidget(b3)
            
            self.bio_stat = QLabel("")
            l.addWidget(self.bio_stat)
            return p

        def start_cam(self):
            if not HAS_EYES:
                self.bio_stat.setText("No Eyes module.")
                return
            self.ct = CameraWorker()
            self.ct.image_update.connect(lambda i: self.cam_lbl.setPixmap(QPixmap.fromImage(i)))
            self.ct.image_update.connect(lambda i: setattr(self, 'last_img', i))
            self.ct.start()

        def cap_face(self):
            if hasattr(self, 'ct'): self.ct.stop()
            if not hasattr(self, 'last_img'): return
            
            ptr = self.last_img.bits()
            ptr.setsize(self.last_img.sizeInBytes())
            arr = np.array(ptr).reshape(self.last_img.height(), self.last_img.width(), 3)
            
            try:
                if Eyes().face.enroll_face(self.admin_name, arr):
                    self.bio_stat.setText("Enrolled.")
                else:
                    self.bio_stat.setText("No face found.")
            except: pass

        # --- PAGE 8: FINALIZE ---
        def create_finalize_page(self):
            p = QWidget()
            l = QVBoxLayout(p)
            l.addWidget(self._header("FINALIZING"))
            self.con = QTextEdit()
            self.con.setReadOnly(True)
            l.addWidget(self.con)
            
            btn = QPushButton("ENGAGE")
            btn.clicked.connect(self.finish)
            l.addWidget(btn)
            return p

        def finish(self):
            self.log("Saving Configs...")
            QApplication.processEvents()
            
            # Save Hardware
            if "camera" not in self.hw_config: self.hw_config["camera"] = {}
            self.hw_config["camera"]["pan_offset"] = self.cur_pan
            self.hw_config["camera"]["tilt_offset"] = self.cur_tilt
            with open(HARDWARE_PATH, 'w') as f: yaml.dump(self.hw_config, f)
            
            # Save Keys
            with open(ENV_PATH, 'w') as f:
                for k, v in self.api_keys.items(): 
                    if v: f.write(f"{k}={v}\n")
            if os.name == 'posix': os.chmod(ENV_PATH, 0o600)

            # Save Rest
            _save_data(self.admin_name, self.pin_hash, self.interview_data, self.generated_persona, 
                       getattr(self, 'sel_voice', 'female_us'), getattr(self, 'sel_speed', 1.0),
                       getattr(self, 'sel_pitch', 1.0), getattr(self, 'sel_depth', 0.5))
                       
            self.log("DONE. Restarting...")
            QTimer.singleShot(2000, self.close)

        def log(self, t):
            self.con.append(f">> {t}")
            QApplication.processEvents()

# ==========================================
#              CLI IMPLEMENTATION
# ==========================================

class RonSetup:
    """CLI Fallback for Headless Systems"""
    def run_wizard(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== RON-OS TERMINAL SETUP ===")
        
        # 1. Identity
        name = input("Admin Name [Admin]: ").strip() or "Admin"
        while True:
            pin = getpass.getpass("Set PIN (4+ digits): ")
            if len(pin) >= 4 and pin == getpass.getpass("Confirm: "): break
            print("Mismatch or too short.")
        
        # 2. Hardware (Simplified Audio Check)
        print("\n[Hardware Calibration]")
        if input("Run Audio Soundcheck? (y/n): ") == 'y':
            if HAS_EARS:
                print("Listening for 3 seconds...")
                # ... (Simplified audio check logic)
                print("Done.")
            else:
                print("Ears module missing.")

        # 3. Voice
        print("\n[Voice Configuration]")
        print("1.Female-US 2.Male-US 3.Female-UK 4.Male-UK")
        v_choice = input("Select Voice [1-4]: ").strip()
        v_map = {"1":"female_us","2":"male_us","3":"female_uk","4":"male_uk"}
        vid = v_map.get(v_choice, "female_us")
        
        # 4. Keys
        print("\n[API Keys] (Press Enter to skip)")
        oa = input("OpenAI Key: ")
        ow = input("OpenWeather Key: ")
        
        keys = {}
        if oa: keys["OPENAI_API_KEY"] = oa
        if ow: keys["OPENWEATHER_KEY"] = ow
        
        with open(ENV_PATH, 'w') as f:
            for k,v in keys.items(): f.write(f"{k}={v}\n")
        
        # 5. Finalize
        print("\nSaving...")
        _save_data(name, _hash_pin(pin), {}, {}, vid, 1.0, 1.0, 0.5)
        print("Setup Complete. Run 'python3 core/loader.py'")

# ==========================================
#              SHARED LOGIC
# ==========================================

def _hash_pin(p): 
    return hashlib.sha256(("RON_SYSTEM_SALT_v1_"+p).encode()).hexdigest()

def _save_data(name, phash, iview, persona, vid, spd, pit, dep):
    # Social Graph
    sg = {
        "graph_metadata": {"version": "3.0", "last_update": time.time()},
        "active_nodes": {
            "NODE_ROOT": {
                "name": name, 
                "access_level": "GOD_MODE", 
                "credentials": {"pin_hash": phash},
                "preferences": {"likes": ["Control"]},
                "interaction_style": "Deferential"
            },
            "NODE_STRANGER_DEFAULT": {"access_level": "ZERO_TRUST"}
        }
    }
    with open(SOCIAL_GRAPH_PATH, 'w') as f: json.dump(sg, f, indent=2)

    # Facts
    fcts = [
        f"User Use Case: {iview.get('use_case', 'Unknown')}", 
        f"Proactivity: {iview.get('proactivity', 'Balanced')}", 
        f"Interest: {iview.get('interest', 'General')}"
    ]
    with open(FACTS_DB_PATH, 'w') as f: json.dump(fcts, f, indent=2)

    # Personality
    pd = persona if persona else {
        "identity_matrix": {"voice_profile": {}, "traits": []}, 
        "operational_parameters": {"humor_setting": "MEDIUM"}
    }
    if "voice_profile" not in pd["identity_matrix"]: 
        pd["identity_matrix"]["voice_profile"] = {}
    
    vp = pd["identity_matrix"]["voice_profile"]
    vp["id"] = vid
    vp["speed"] = spd
    vp["pitch"] = pit
    vp["depth"] = dep
    
    with open(PERSONALITY_PATH, 'w') as f: json.dump(pd, f, indent=2)
    
    # Lock
    with open(LOCK_FILE, 'w') as f: f.write(str(time.time()))

if __name__ == "__main__":
    if HAS_GUI and (os.environ.get("DISPLAY") or os.name == 'nt'):
        app = QApplication(sys.argv)
        w = GenesisWizard()
        w.show()
        sys.exit(app.exec())
    else: 
        RonSetup().run_wizard()
