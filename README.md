# attend

**AI-Powered Real-Time Facial Recognition Attendance Management System**

Fully offline • CPU-only • Windows desktop application

---

## Overview

attend is a local Python desktop application that marks student attendance using real-time facial recognition from a webcam. It requires **no cloud services, no web server, and no NVIDIA GPU**.

### Key Features

- Real-time multi-face detection + proximity-based primary face selection
- ArcFace embeddings (InsightFace) + FAISS similarity search
- Persistent face tracking to avoid duplicate marks
- Two configurable daily attendance sessions (independent records)
- Unknown face capture with 7-day retention
- Bulk student enrollment from photos
- Manual admin override for attendance
- SQLite database + encrypted biometric storage support
- Live dashboard with activity feed and basic analytics hooks

---

## Requirements

- Windows 10/11 (primary target)
- Python 3.10 – 3.12 recommended
- Webcam
- ~2–4 GB free disk (models + data)
- CPU with AVX support preferred

### Python Dependencies

See `requirements.txt`. Main packages:

- `PySide6` – GUI
- `opencv-python-headless`
- `insightface` + `onnxruntime` – face detection & ArcFace recognition
- `faiss-cpu` – vector search
- `SQLAlchemy` – database
- `cryptography` – optional encryption helpers

---

## Quick Start

```bash
# 1. Clone / extract the project
cd attend

# 2. Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. First run will download InsightFace models (buffalo_l) into ./models
#    This can take a few minutes depending on internet speed.

# 5. Launch
python -m app.main
```

---

## Project Structure

```
attend/
├── app/
│   ├── main.py                 # Entry point
│   ├── core/
│   │   ├── config.py           # Paths, thresholds, session times
│   │   ├── database.py         # SQLite + repositories
│   │   ├── models.py           # SQLAlchemy models
│   │   └── security.py         # Encryption helpers
│   ├── vision/
│   │   ├── pipeline.py         # Main recognition pipeline
│   │   ├── recognizer.py       # InsightFace + FAISS
│   │   ├── tracker.py          # Multi-face tracker
│   │   └── quality.py          # Blur / size / pose checks
│   ├── services/
│   │   ├── attendance_service.py
│   │   └── enrollment.py
│   ├── ui/
│   │   └── main_window.py      # PySide6 GUI
│   └── utils/
│       ├── camera.py
│       └── logging_setup.py
├── data/                       # Created at runtime
│   ├── attend.db
│   ├── faces/                  # Registered student photos
│   ├── unknowns/
│   └── faiss_index/
├── models/                     # InsightFace ONNX models
├── requirements.txt
└── README.md
```

---

## Usage Guide

### 1. Enroll Students

- Go to **Enrollment** tab
- Enter Student ID + Name (required)
- Choose a clear frontal photo
- Click **Enroll Student**
- Or use **Bulk Enroll from Folder** – files named `STUDENTID_Name.jpg`

After enrollment the FAISS index is automatically rebuilt.

Bulk photo naming convention:

- Use STUDENTID_Name.jpg (for example, S001_Alex_Smith.jpg) to set both the student ID and name. Underscores in the name become spaces.
- Use STUDENTID.jpg (for example, S001.jpg) to use the student ID as the name.
- Supported formats: .jpg, .jpeg, .png, and .bmp. Select the folder containing the photos in the app.

### 2. Live Attendance

- Ensure a session is active (default: 09:00–13:00 and 14:00–18:00)
- Stand in front of the camera
- The system selects the primary (closest/largest) face
- On successful match → “Attendance Marked Successfully”
- Repeat appearances in the same session → “Attendance Already Marked”

### 3. Manual Override

- Use the **Manual Mark** tab if the camera or recognition fails
- Provide Student ID and optional reason
- Action is logged as an admin override

### 4. Settings

- Adjust match threshold (default ≈ 0.42 cosine)
- Configure the two daily session start/end times

---

## Important Notes

### First Run Model Download

InsightFace will download the `buffalo_l` model pack on first launch.  
Ensure you have internet access once. After that the system works fully offline.

### Performance Targets

- Designed for CPU-only inference
- Aim for sub-300 ms recognition latency under controlled conditions
- Frame skipping, smaller detection size, and tracking reduce load

### Privacy & Security

- All photos, embeddings and attendance records stay on the local machine
- Optional Fernet encryption helpers are provided for biometric data
- Implement institutional consent and retention policies before production use

### Known Limitations / Future Work

- Liveness detection is not yet implemented (spoofing risk exists)
- Unknown-face gallery UI is a placeholder
- Advanced analytics charts can be added
- Depth-based proximity is not used (no depth camera required)
- Thorough accuracy evaluation under varied lighting/angles is still required

---

## Development

```bash
# Run tests (add your own)
pytest tests/

# Format
black app/
```

---

## License

This project is provided as a foundation for educational and institutional use.  
Review and comply with local biometric data protection regulations before deployment.

---

**Author**: Abhiraj Adhikary  
**Institution**: Haldia Institute of Technology
