import time
import random
import platform
import os
import sys
import importlib

# --- DIAGNOSTIC COLORS ---
HEADER = '\033[95m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'

class RonDiagnostics:
    """
    The updated diagnostic tool. Run this to check system health.
    """
    @staticmethod
    def run_system_check(required_files):
        print(f"{HEADER}{BOLD}RON SYSTEM DIAGNOSTIC PROTOCOL{ENDC}")
        print(f"Host: {platform.node()} ({platform.system()})")
        
        all_ok = True
        
        # 1. File Integrity
        print(f"\n{BOLD}[PHASE 1] File Integrity Check{ENDC}")
        for desc, path in required_files.items():
            if os.path.exists(path):
                print(f" {OKGREEN}[PASS]{ENDC} Found {desc}")
            else:
                print(f" {FAIL}[FAIL]{ENDC} Missing {desc} at {path}")
                all_ok = False

        # 2. Hardware Detection
        print(f"\n{BOLD}[PHASE 2] Environment Detection{ENDC}")
        if RonDiagnostics.is_raspberry_pi():
            print(f" {OKGREEN}[HW]{ENDC} Raspberry Pi Logic Board Detected.")
        else:
            print(f" {WARNING}[SIM]{ENDC} Non-Pi Environment. Engaging Mock Drivers.")

        return all_ok

    @staticmethod
    def is_raspberry_pi():
        try:
            with open('/proc/device-tree/model', 'r') as f:
                if 'Raspberry Pi' in f.read(): return True
        except:
            pass
        return False

# --- MOCK HARDWARE CLASSES ---
# These are loaded when real hardware is absent to prevent crashes.

class MockGPIO:
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = 1
    LOW = 0

    @staticmethod
    def setmode(mode):
        print(f"{WARNING}[MOCK GPIO]{ENDC} Mode set to {mode}")

    @staticmethod
    def setup(pin, mode):
        pass # Silent success

    @staticmethod
    def output(pin, state):
        state_str = "HIGH" if state else "LOW"
        # Only log significant changes to avoid spamming stdout
        # print(f"{WARNING}[MOCK GPIO]{ENDC} Pin {pin} -> {state_str}")

    @staticmethod
    def cleanup():
        print(f"{WARNING}[MOCK GPIO]{ENDC} Cleanup executed.")

class MockCamera:
    def capture(self, filename):
        print(f"{WARNING}[MOCK CAM]{ENDC} *Click* (Saved blank image to {filename})")
        # Create a dummy file so file checks pass
        with open(filename, 'w') as f:
            f.write("mock_image_data")

class MockSenseHat:
    def show_message(self, text, scroll_speed=0.1):
        print(f"{WARNING}[MOCK LED]{ENDC} Scrolling: '{text}'")
    
    def clear(self):
        print(f"{WARNING}[MOCK LED]{ENDC} Cleared.")
    
    def get_temperature(self):
        return random.uniform(35.0, 45.0)  # Return realistic CPU temp
