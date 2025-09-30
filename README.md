# Codex Sorter

A lightweight Python/OCR pipeline that reads a Magic: The Gathering card’s **set code** and **collector number**, looks it up on Scryfall, and returns the official card name.  
Designed to be the “brain” of an automated sorter – the mechanical parts (head & tray) are provided as STL files.

---  

## What It Does

| Step | Description |
|------|-------------|
| **Capture** | Grab a single frame from a webcam (or Pi Camera). |
| **Pre‑process** | Crop → grayscale → invert for clean OCR. |
| **OCR** | Tiny Tesseract call (`mini_ocr`) limited to the characters that appear in set/collector numbers. |
| **Parse** | Extract numeric collector number and three‑letter set code from the OCR result. |
| **Lookup** | Query Scryfall (`https://api.scryfall.com/cards/{set}/{num}`) for the card JSON. |
| **Return** | Print (or forward) the official card name – ready to be fed into a sorting routine. |

> **Note:** The script only works on *new‑style* cards that have set initials in the bottom left corner below the collector ID.
> One generation older layouts may work with custom ROI adjustments.

---  

## Hardware (what we use today)

| Component | Role |
|-----------|------|
| **Prusa XL** | 6‑axis Cartesian frame that moves the sorting head with high precision. |
| **USB webcam / Pi Camera** | Provides the image for OCR. |
| **Raspberry Pi 5** (or any Linux box) | Runs the Python script, talks to the camera and to Scryfall over Wi‑Fi/Ethernet. |
| **Sorting Head (STL)** | Holds the camera at a fixed distance, includes a simple light guide. |
| **Sorting Tray (STL)** | Slots for each set; cards are dropped into the correct bin after identification. |

---  

## Quick Setup (Raspberry Pi 5)

```bash
# 1️⃣ OS deps
sudo apt update && sudo apt install -y python3-pip tesseract-ocr libtesseract-dev v4l-utils

# 2️⃣ Python env
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # opencv, numpy, pytesseract, requests

# 3️⃣ Test the camera
v4l2-ctl --list-devices          # should show /dev/video0
fswebcam test.jpg                # verify you get a clear picture

# 4️⃣ Run
python card_sorter.py
```

The script will save a few debug PNGs (`debug_*.png`) in the working directory if `DEBUG=True`.  

---  

## How It Fits Into a Full Sorter

1. **Home** – Prusa XL moves the head to a *scan position* above the incoming card stack.  
2. **Capture & Identify** – `card_sorter.py` runs, returns the card name.  
3. **Decision** – Simple lookup table maps each set code to a tray slot.  
4. **Deposit** – Prusa XL moves the head over the appropriate bin and releases the card (gravity‑feed or tiny servo).  

---  

## Aspirational Roadmap

| Goal | Why it matters |
|------|----------------|
| **Open‑source electronics kit** – Raspberry Pi Zero 2 W + stepper driver board, ready‑to‑wire to a Creality Ender 3 frame. | Lowers the entry cost; makes the sorter accessible to hobbyists without a Prusa XL. |
| **Modular firmware** – separate “camera service”, “motion service”, and “sorting logic” that communicate over MQTT or gRPC. | Enables mixed‑hardware setups (e.g., Ender 3 + Pi Zero). |
| **Full‑stack UI** – web dashboard to monitor progress, adjust ROI, add new set‑to‑tray mappings on the fly. | Improves usability for tournaments and collectors. |
| **Support older cards** – adaptive ROI detection, optional colour‑filter pre‑processing. | Extends usefulness to legacy collections. |

---  

## Contributing

* Fork the repo, create a feature branch, and submit a Pull Request.  
* Keep code Python 3.10+ compatible; add any new dependencies to `requirements.txt`.  

---  

## License
