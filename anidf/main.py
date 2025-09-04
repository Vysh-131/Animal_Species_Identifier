import os
import json
import threading
import platform
import subprocess
import urllib.parse
from datetime import datetime

import pandas as pd
from PIL import Image, ImageTk
from PIL.ExifTags import TAGS
from transformers import pipeline

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Try ttkbootstrap theme, fall back to plain Tk if not available
try:
    import ttkbootstrap as tb
    HAS_TTKBOOTSTRAP = True
except Exception:
    HAS_TTKBOOTSTRAP = False

# ===== Paths & Constants =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
LOGO_PATH = os.path.join(IMAGES_DIR, "logo.jpeg")
LOCAL_MODEL_DIR = os.path.join(BASE_DIR, "models", "eva02_inat21")
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "progress.json")
DEFAULT_EXCEL = os.path.join(OUTPUT_DIR, "results.xlsx")

# ===== Helpers =====
def safe_makedirs(path: str):
    os.makedirs(path, exist_ok=True)

def extract_metadata(img_path):
    """Return dict with 'Date' and 'Time' from EXIF DateTime, if present."""
    date, time = None, None
    try:
        img = Image.open(img_path)
        info = img._getexif()
        if info:
            for tag, value in info.items():
                if TAGS.get(tag, tag) == "DateTime":
                    parts = str(value).split(" ")
                    if len(parts) == 2:
                        date = parts[0].replace(":", "-")
                        time = parts[1]
                    break
    except Exception:
        pass
    return {"Date": date, "Time": time}

def parse_path_parts(img_path):
    """Extract Block, Camera ID, Animal Folder from path."""
    parts = img_path.split(os.sep)
    animal_folder = parts[-2] if len(parts) >= 2 else None
    camera_id     = parts[-3] if len(parts) >= 3 else None
    block         = parts[-4] if len(parts) >= 4 else None
    return animal_folder, block, camera_id

def build_hyperlink_for_animal(name):
    """Return Excel HYPERLINK formula for animal name."""
    label = name if name else "Unidentified"
    query = urllib.parse.quote_plus(label if label.lower() != "unidentified" else "wildlife+image+unidentified")
    url = f"https://www.google.com/search?q={query}"
    return f'=HYPERLINK("{url}", "{label}")'

def save_to_excel(records, output_path=DEFAULT_EXCEL):
    safe_makedirs(os.path.dirname(output_path))
    df = pd.DataFrame(records)
    preferred_cols = ["Animal Folder", "Block", "Camera ID", "Animal Name", "Date", "Time"]
    cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
    df = df[cols]
    df.to_excel(output_path, index=False)
    return output_path

def open_folder(path):
    try:
        if platform.system() == 'Windows':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as e:
        messagebox.showwarning("Open Folder", f"Could not open folder:\n{e}")

def zenity_pick_dir(title="Select Input Folder"):
    """Try zenity on Linux; fallback to Tk dialog elsewhere."""
    if platform.system() == "Linux":
        try:
            proc = subprocess.run(
                ['zenity', '--file-selection', '--directory', f'--title={title}'],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if proc.returncode == 0:
                path = proc.stdout.strip()
                if path:
                    return path
        except Exception:
            pass
    return filedialog.askdirectory(title=title)

# ===== Processor =====
class Processor:
    def __init__(self, app):
        self.app = app
        self.classifier = None
        self.stop_flag = False
        self.records = []
        self.processed_paths = set()
        self.root_folder = None
        self.batch_size = 16
        self.conf_threshold = 0.85

    def set_params(self, root_folder, batch_size, conf_threshold):
        self.root_folder = root_folder
        self.batch_size = batch_size
        self.conf_threshold = conf_threshold

    def reset_state(self):
        self.stop_flag = False
        self.records = []
        self.processed_paths = set()

    def load_model(self):
        self.app.set_status("Loading EVA02 model...")
        if not os.path.isdir(LOCAL_MODEL_DIR):
            raise FileNotFoundError(f"Local model not found at: {LOCAL_MODEL_DIR}")
        self.classifier = pipeline("image-classification", model=LOCAL_MODEL_DIR)
        self.app.set_status("Model loaded.")

    def _scan_all_images(self):
        paths = []
        for root, _, files in os.walk(self.root_folder):
            for f in files:
                if f.startswith("._"):
                    continue
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    full = os.path.join(root, f)
                    if full not in self.processed_paths:
                        paths.append(full)
        return paths

    def _save_progress(self):
        safe_makedirs(OUTPUT_DIR)
        try:
            payload = {
                "meta": {
                    "root_folder": self.root_folder,
                    "batch_size": self.batch_size,
                    "confidence_threshold": self.conf_threshold,
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                },
                "records": self.records,
                "processed_paths": list(self.processed_paths),
            }
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"Progress save error: {e}")

    def _load_progress(self):
        if not os.path.isfile(PROGRESS_FILE):
            return False
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            meta = payload.get("meta", {})
            self.root_folder = meta.get("root_folder", self.root_folder)
            self.batch_size = int(meta.get("batch_size", self.batch_size))
            self.conf_threshold = float(meta.get("confidence_threshold", self.conf_threshold))
            self.records = payload.get("records", [])
            self.processed_paths = set(payload.get("processed_paths", []))
            return True
        except Exception as e:
            messagebox.showwarning("Resume", f"Could not load progress.json:\n{e}")
            return False

    def stop(self):
        self.stop_flag = True
        self.app.set_status("Stopping after current image...")

    def _classify_batch(self, batch_paths):
        try:
            results = self.classifier(batch_paths, top_k=1)
            normalized = []
            for item in results:
                if isinstance(item, list) and item:
                    normalized.append(item[0])
                elif isinstance(item, dict):
                    normalized.append(item)
                else:
                    normalized.append({"label": "Unidentified", "score": 0.0})
            return normalized
        except Exception:
            out = []
            for p in batch_paths:
                try:
                    r = self.classifier(p, top_k=1)
                    if isinstance(r, list) and r:
                        out.append(r[0])
                    elif isinstance(r, dict):
                        out.append(r)
                    else:
                        out.append({"label": "Unidentified", "score": 0.0})
                except Exception:
                    out.append({"label": "Unidentified", "score": 0.0})
            return out

    def _record_from_path_and_result(self, img_path, result):
        label = (result.get("label") or "Unidentified")
        score = float(result.get("score", 0.0))
        animal_name = label.split(",")[0].strip()
        if score < self.conf_threshold:
            animal_name = "Unidentified"
        meta = extract_metadata(img_path)
        animal_folder, block, camera_id = parse_path_parts(img_path)
        return {
            "Animal Folder": animal_folder,
            "Block": block,
            "Camera ID": camera_id,
            "Animal Name": build_hyperlink_for_animal(animal_name),
            "Date": meta.get("Date"),
            "Time": meta.get("Time"),
            "Path": img_path
        }

    def process_new(self):
        try:
            self.reset_state()
            self.load_model()
        except Exception as e:
            self.app.enable_ui()
            messagebox.showerror("Model Error", str(e))
            return
        all_paths = self._scan_all_images()
        if not all_paths:
            self.app.enable_ui()
            messagebox.showinfo("No Images", "No images found in the selected folder.")
            return
        self.app.progress_bar["maximum"] = len(all_paths)
        self.app.progress_bar["value"] = 0
        for i in range(0, len(all_paths), self.batch_size):
            if self.stop_flag:
                break
            batch = all_paths[i:i + self.batch_size]
            results = self._classify_batch(batch)
            for j, img_path in enumerate(batch):
                if self.stop_flag:
                    break
                rec = self._record_from_path_and_result(img_path, results[j])
                self.records.append(rec)
                self.processed_paths.add(img_path)
                self.app.progress_bar["value"] = len(self.processed_paths)
                self.app.set_status(f"Processed {len(self.processed_paths)}/{len(all_paths)} images")
            self._save_progress()
        self._finalize_processing()

    def process_resume(self):
        if not self._load_progress():
            self.app.enable_ui()
            return
        try:
            if self.classifier is None:
                self.load_model()
        except Exception as e:
            self.app.enable_ui()
            messagebox.showerror("Model Error", str(e))
            return
        remaining = self._scan_all_images()
        total = len(remaining) + len(self.processed_paths)
        if total == 0:
            self.app.enable_ui()
            messagebox.showinfo("Resume", "Nothing to process.")
            return
        self.app.progress_bar["maximum"] = total
        self.app.progress_bar["value"] = len(self.processed_paths)
        for i in range(0, len(remaining), self.batch_size):
            if self.stop_flag:
                break
            batch = remaining[i:i + self.batch_size]
            results = self._classify_batch(batch)
            for j, img_path in enumerate(batch):
                if self.stop_flag:
                    break
                rec = self._record_from_path_and_result(img_path, results[j])
                self.records.append(rec)
                self.processed_paths.add(img_path)
                self.app.progress_bar["value"] = len(self.processed_paths)
                self.app.set_status(f"Processed {len(self.processed_paths)}/{total} images")
            self._save_progress()
        self._finalize_processing()

    def _finalize_processing(self):
        export_records = []
        for r in self.records:
            export_records.append({
                "Animal Folder": r.get("Animal Folder"),
                "Block": r.get("Block"),
                "Camera ID": r.get("Camera ID"),
                "Animal Name": r.get("Animal Name"),
                "Date": r.get("Date"),
                "Time": r.get("Time"),
            })
        output_file = save_to_excel(export_records, DEFAULT_EXCEL)
        self._save_progress()
        self.app.set_status("✅ Exported to Excel")
        messagebox.showinfo("Done", f"Results saved to:\n{output_file}")
        self.app.enable_ui()

# ===== GUI =====
class AnimalClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MOLECULAR BIODIVERSITY LAB, OOTY")
        self.root.geometry("780x640")
        self.root.resizable(False, False)

        # === File Menu ===
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Start New", command=self.start_new)
        filemenu.add_command(label="Resume Previous", command=self.resume_previous)
        filemenu.add_command(label="Resume Later", command=self.stop_and_save)
        filemenu.add_command(label="Stop & Save Now", command=self.stop_and_save)
        filemenu.add_separator()
        filemenu.add_command(label="Export Excel from progress.json", command=self.export_from_json)
        filemenu.add_command(label="Open Results Folder", command=lambda: open_folder(OUTPUT_DIR))
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.root.config(menu=menubar)

        # Main layout
        main = ttk.Frame(root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # Logo
        logo_frame = ttk.Frame(main)
        logo_frame.grid(row=0, column=0, columnspan=6, pady=(0, 16))
        try:
            img = Image.open(LOGO_PATH)
            img = img.resize((240, 120), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(img)
            ttk.Label(logo_frame, image=self.logo_photo).pack()
        except Exception as e:
            print(f"Logo load failed: {e}")

        # Start/Stop buttons
        btns = ttk.Frame(main)
        btns.grid(row=1, column=0, columnspan=6, pady=(0, 18))
        self.start_btn = ttk.Button(btns, text="▶ Start", command=self.start_new)
        self.start_btn.pack(side=tk.LEFT, padx=12)
        self.stop_btn = ttk.Button(btns, text="⏹ Stop", command=self.stop_and_save)
        self.stop_btn.pack(side=tk.LEFT, padx=12)

        # Input folder
        ttk.Label(main, text="Input Folder:").grid(row=2, column=0, sticky="w")
        self.path_entry = ttk.Entry(main)
        self.path_entry.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(0, 8))
        self.browse_btn = ttk.Button(main, text="Browse", command=self.browse_folder)
        self.browse_btn.grid(row=3, column=5, padx=(8, 0), sticky="ew")

        # Parameters
        ttk.Label(main, text="Batch Size:").grid(row=4, column=0, sticky="w")
        self.batch_entry = ttk.Entry(main, width=10)
        self.batch_entry.insert(0, "16")
        self.batch_entry.grid(row=4, column=1, sticky="w")

        ttk.Label(main, text="Confidence Threshold:").grid(row=4, column=2, sticky="w", padx=(12, 0))
        self.conf_entry = ttk.Entry(main, width=10)
        self.conf_entry.insert(0, "0.85")
        self.conf_entry.grid(row=4, column=3, sticky="w")

        # Progress/status
        self.progress_bar = ttk.Progressbar(main, orient="horizontal", mode="determinate", length=100)
        self.progress_bar.grid(row=5, column=0, columnspan=6, sticky="ew", pady=(24, 6))
        self.status_label = ttk.Label(main, text="Ready.")
        self.status_label.grid(row=6, column=0, columnspan=6, sticky="w", pady=(4, 0))

        # Footer
        self.dev_label = ttk.Label(root, text="Vysh131", font=("TkDefaultFont", 8, "italic"))
        self.dev_label.pack(side=tk.BOTTOM, anchor=tk.E, padx=6, pady=6)

        for c in range(6):
            main.columnconfigure(c, weight=1)

        self.processor = Processor(self)

    def set_status(self, msg):
        self.status_label.config(text=msg)
        self.root.update_idletasks()

    def enable_ui(self):
        for w in [self.start_btn, self.stop_btn, self.browse_btn]:
            try: w.config(state=tk.NORMAL)
            except Exception: pass

    def disable_ui(self):
        for w in [self.start_btn, self.stop_btn, self.browse_btn]:
            try: w.config(state=tk.DISABLED)
            except Exception: pass

    def browse_folder(self):
        folder = zenity_pick_dir("Select Input Folder")
        if folder:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def start_new(self):
        folder = self.path_entry.get()
        if not folder:
            messagebox.showerror("Error", "Please select an input folder.")
            return
        try:
            batch_size = int(self.batch_entry.get())
            conf = float(self.conf_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Batch size and confidence threshold must be numbers.")
            return
        if os.path.isfile(PROGRESS_FILE):
            if not messagebox.askyesno("Start New", "Existing progress found. Overwrite?"):
                return
            try: os.remove(PROGRESS_FILE)
            except Exception: pass
        self.disable_ui()
        self.set_status("Starting new processing...")
        self.processor.set_params(folder, batch_size, conf)
        t = threading.Thread(target=self.processor.process_new, daemon=True)
        t.start()

    def resume_previous(self):
        if not os.path.isfile(PROGRESS_FILE):
            messagebox.showinfo("Resume", "No progress.json found to resume.")
            return
        self.disable_ui()
        self.set_status("Resuming from previous session...")
        t = threading.Thread(target=self.processor.process_resume, daemon=True)
        t.start()

    def stop_and_save(self):
        self.processor.stop()

    def export_from_json(self):
        if not os.path.isfile(PROGRESS_FILE):
            messagebox.showinfo("Export", "No progress.json found.")
            return
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            recs = payload.get("records", [])
            export_records = []
            for r in recs:
                export_records.append({
                    "Animal Folder": r.get("Animal Folder"),
                    "Block": r.get("Block"),
                    "Camera ID": r.get("Camera ID"),
                    "Animal Name": r.get("Animal Name"),
                    "Date": r.get("Date"),
                    "Time": r.get("Time"),
                })
            out = save_to_excel(export_records, DEFAULT_EXCEL)
            messagebox.showinfo("Export", f"Excel exported to:\n{out}")
            open_folder(os.path.dirname(out))
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
        finally:
            self.enable_ui()

# ===== Run =====
if __name__ == "__main__":
    if HAS_TTKBOOTSTRAP:
        root = tb.Window(themename="cyborg")
    else:
        root = tk.Tk()
    app = AnimalClassifierApp(root)
    root.mainloop()
