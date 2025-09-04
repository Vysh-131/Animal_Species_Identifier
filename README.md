#  Animal Classifier for Camera Trap Images  
This project was developed for the **Molecular Biodiversity Lab, Ooty (MBL)** to automate species identification from camera trap images.  
It uses the **EVA02 (inat21 fine-tuned) model** from Hugging Face to classify wildlife images and exports results into a structured **Excel file** with metadata. 

## Features

- Process an entire folder of camera trap images  
-  Classify animals using the EVA02-inat21 model  
-  Extract metadata (Date, Time from EXIF)  
-  Export results into **Excel (.xlsx)** with:  
  - **Animal Name** (with Google search hyperlink for cross-verification)  
  - **Block ID** (e.g., MM-073)  
  - **Camera ID** (e.g., CT-072-MC-011)  
  - **Folder Name** (animal folder)  
  - **Date & Time**  
-  Resume Later / Resume Previous operations using `progress.json`  
-  Stop & Save Now during processing  
-  Menu options to **Export from progress.json** and **Open results folder**  
-  GUI with theme + logo support (using `ttkbootstrap`)  
#  Animal Classifier for Camera Trap Images  

![Logo](images/logo.jpeg)

This project was developed for the **Molecular Biodiversity Lab (MBL)** to automate species identification from camera trap images.  
It uses the **EVA02 (inat21 fine-tuned) model** from Hugging Face to classify wildlife images and exports results into a structured **Excel file** with metadata.  

---

## ✨ Features

- 📂 Process an entire folder of camera trap images  
- 🔍 Classify animals using the EVA02-inat21 model  
- 📑 Extract metadata (Date, Time from EXIF)  
- 📊 Export results into **Excel (.xlsx)** with:  
  - **Animal Name** (with Google search hyperlink for cross-verification)  
  - **Block ID** (e.g., MM-073)  
  - **Camera ID** (e.g., CT-072-MC-011)  
  - **Folder Name** (animal folder)  
  - **Date & Time**  
- ⏸️ Resume Later / Resume Previous operations using `progress.json`  
- ⏹️ Stop & Save Now during processing  
- 📁 Menu options to **Export from progress.json** and **Open results folder**  
- 🖼️ GUI with theme + logo support (using `ttkbootstrap`)  

---

## 📦 Installation

### Requirements
- Python 3.10+ recommended  
- Works on **Windows, macOS, Linux**  

### 1. Clone the repository
```bash
git clone https://github.com/Vysh-131/animal_df.git
cd animal_df 

### 2. Install dependencies

pip install -r requirements.txt

(If you face PyTorch installation issues, install it separately following PyTorch instructions

.)
