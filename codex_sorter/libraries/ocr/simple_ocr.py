# ----------------------------------------------------------------------
#   codex_sorter/libraries/ocr/simple_ocr.py
# ----------------------------------------------------------------------
"""
Minimal OCR utilities for the card‑sorting robot.

* The low‑level pipeline (`mini_ocr`) runs a tiny preprocessing step,
  then hands the image to **pytesseract**.
* `preprocessing` (rotate → crop) mirrors the exact steps you used before.
* `img_to_name` ties everything together:
      – capture → OCR → parse set‑code & collector number
      – query Scryfall for the official card name
      – return that name (or ``""`` on any failure).

All heavy lifting is logged via the project's central logger; every function
returns a value rather than raising, which keeps the main sorting loop robust
on a low‑powered Raspberry Pi Zero.
"""

from __future__ import annotations

import re
import pathlib
from typing import Optional, Tuple

import cv2
import numpy as np
import pytesseract
import requests

# ----------------------------------------------------------------------
#   Local imports – keep the same absolute style used elsewhere
# ----------------------------------------------------------------------
from ..config import OCR_WHITELIST, SCRYFALL_CARD_URL
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

__all__ = [
    "mini_ocr",
    "preprocessing",
    "rotate_image",
    "crop_image",
    "number_extraction",
    "set_extraction",
    "get_line",
    "fetch_card",
    "extract_name",
    "img_to_name",
]

# ----------------------------------------------------------------------
#   Helper constants
# ----------------------------------------------------------------------
_DEBUG_OCR_DUMP = pathlib.Path("debug_ocr")  # folder for optional debug images
_DEBUG_OCR_DUMP.mkdir(exist_ok=True)


# ----------------------------------------------------------------------
#   Low‑level OCR (unchanged logic, but safer & typed)
# ----------------------------------------------------------------------
def mini_ocr(image: np.ndarray) -> str:
    """
    Run a very light preprocessing step and return the raw OCR string.

    The original code inverted the greyscale image; we keep that because it
    produced the best results on your test cards.  Errors are caught so the
    caller never crashes – an empty string is returned instead.

    Parameters
    ----------
    image : np.ndarray
        BGR image (as supplied by OpenCV).

    Returns
    -------
    str
        The OCR‑extracted text stripped of surrounding whitespace.
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        inverted = cv2.bitwise_not(gray)

        # Optional – keep a copy for offline debugging.  This is cheap on the Pi
        # and can be turned off by setting ``_DEBUG_OCR_DUMP`` to ``None``.
        if _DEBUG_OCR_DUMP:
            dump_path = _DEBUG_OCR_DUMP / "mini_ocr.png"
            cv2.imwrite(str(dump_path), inverted)

        cfg = f"-c tessedit_char_whitelist={OCR_WHITELIST} --psm 4"
        text = pytesseract.image_to_string(inverted, config=cfg)
        return text.strip()
    except Exception as exc:   # pragma: no cover – defensive
        log.error("mini_ocr failed: %s", exc)
        return ""


# ----------------------------------------------------------------------
#   Pre‑processing helpers (rotate → crop)
# ----------------------------------------------------------------------
def rotate_image(
    img: np.ndarray,
    angle_deg: float,
    keep_size: bool = False,
) -> np.ndarray:
    """
    Rotate ``img`` by *angle_deg* degrees.

    Parameters
    ----------
    img : np.ndarray
        Input image.
    angle_deg : float
        Rotation angle (positive → counter‑clockwise).
    keep_size : bool, optional
        If ``True`` the output canvas keeps the original dimensions; otherwise
        it expands to contain the whole rotated image.

    Returns
    -------
    np.ndarray
        The rotated image.
    """
    h, w = img.shape[:2]
    centre = (w // 2, h // 2)

    rot_mat = cv2.getRotationMatrix2D(centre, angle_deg, scale=1.0)

    if keep_size:
        # Simple warp – we lose corners but stay in the original frame.
        return cv2.warpAffine(
            img,
            rot_mat,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # Compute new bounding box size so the whole image fits.
    cos = abs(rot_mat[0, 0])
    sin = abs(rot_mat[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    rot_mat[0, 2] += (new_w / 2) - centre[0]
    rot_mat[1, 2] += (new_h / 2) - centre[1]

    return cv2.warpAffine(
        img,
        rot_mat,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def crop_image(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """
    Safe cropping – clamps coordinates to the image bounds.

    Parameters
    ----------
    img : np.ndarray
        Source image.
    x, y : int
        Top‑left corner of the desired crop area.
    w, h : int
        Width and height of the crop rectangle.

    Returns
    -------
    np.ndarray
        The cropped region (always at least 1 px×1 px).
    """
    img_h, img_w = img.shape[:2]

    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))

    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))

    return img[y : y + h, x : x + w]


def preprocessing(image_input: np.ndarray) -> np.ndarray:
    """
    Rotate the raw camera frame 180° and then crop to the region that
    contains the printed card text.  The numeric values (`200,370,800,90`)
    match the geometry of your hopper‑to‑head setup.

    Returns
    -------
    np.ndarray
        Image ready for ``mini_ocr``.
    """
    rotated = rotate_image(image_input, angle_deg=180)
    return crop_image(rotated, x=200, y=370, w=800, h=90)


# ----------------------------------------------------------------------
#   Text‑parsing helpers (extract number / set code from OCR output)
# ----------------------------------------------------------------------
def number_extraction(txt: str) -> str:
    """
    Pull the numeric collector number from a raw OCR line.

    * If the line contains a ``/`` we keep only the part before it.
    * When four digits are present we drop a leading zero (your original rule).

    Returns an empty string if no digits are found.
    """
    if "/" in txt:
        txt = txt.split("/", maxsplit=1)[0]

    digits = [ch for ch in txt if ch.isdigit()]

    # Drop a leading zero when the collector number is 4 digits long
    if len(digits) == 4:
        digits = digits[1:]

    return "".join(digits)


def set_extraction(txt: str) -> str:
    """
    Return (uppercase) the first three characters of a line – conventionally
    the set code on Magic cards.
    """
    return txt[:3].upper()


def get_line(text: str, line_num: int) -> str:
    """
    Find the *line* that contains at least three digits (the collector‑number
    line).  Return the line ``line_num`` positions after it – ``0`` returns the
    numeric line itself.

    Falls back to a simple index lookup if no such “anchor” line exists.
    """
    lines = text.splitlines()
    digit_pat = re.compile(r"\d")

    anchor_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if sum(1 for _ in digit_pat.finditer(line)) >= 3:
            anchor_idx = i
            break

    if anchor_idx is None:
        # No obvious numeric line → just use the raw index.
        return lines[line_num] if 0 <= line_num < len(lines) else ""

    target_idx = anchor_idx + line_num
    return (
        lines[target_idx]
        if 0 <= target_idx < len(lines)
        else ""
    )


# ----------------------------------------------------------------------
#   Scryfall API helpers
# ----------------------------------------------------------------------
def fetch_card(set_code: str, collector_number: str) -> Optional[dict]:
    """
    Query the public Scryfall API for a card.

    Parameters
    ----------
    set_code : str
        Three‑letter set identifier (case‑insensitive).
    collector_number : str
        Numeric collector number extracted from the OCR output.

    Returns
    -------
    dict or None
        JSON payload on success, ``None`` on HTTP error / 404.
    """
    url = SCRYFALL_CARD_URL.format(
        set_code=set_code.lower(),
        collector_number=collector_number,
    )
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        log.warning("Scryfall: no card for %s #%s", set_code.upper(), collector_number)
        return None
    except Exception as exc:   # pragma: no cover – defensive
        log.error("Scryfall request failed: %s", exc)
        return None


def extract_name(card_data: Optional[dict]) -> str:
    """
    Pull the ``name`` field from a Scryfall JSON payload.

    Returns an empty string if the payload is missing or malformed.
    """
    if not card_data:
        return ""
    return card_data.get("name", "")


# ----------------------------------------------------------------------
#   High‑level convenience function
# ----------------------------------------------------------------------
def img_to_name(image: np.ndarray) -> str:
    """
    End‑to‑end pipeline:

      1. Pre‑process the raw frame (rotate → crop).  
      2. Run a light OCR pass (`mini_ocr`).  
      3. Parse *set code* & *collector number* from the OCR text.  
      4. Query Scryfall for the official card name.  

    If **any** step fails, an empty string is returned so the caller can decide
    to retry or skip the card.

    Parameters
    ----------
    image : np.ndarray
        Raw BGR frame captured by the camera.

    Returns
    -------
    str
        Official card name (e.g., “Lightning Bolt”) or ``""`` on failure.
    """
    # 1️⃣ Pre‑process → focus only on the text region
    cropped = preprocessing(image)

    # 2️⃣ OCR raw text
    raw_text = mini_ocr(cropped)
    log.debug("OCR raw output:\n%s", raw_text)

    if not raw_text:
        return ""

    # 3️⃣ Extract set code & collector number from the appropriate lines.
    #     Line 0 – numeric line, Line 1 – set‑code line (matches original script).
    number = number_extraction(get_line(raw_text, 0))
    set_code = set_extraction(get_line(raw_text, 1))

    if not number or not set_code:
        log.warning("Failed to parse set/number from OCR text")
        return ""

    log.info("Parsed → Set: %s, Number: %s", set_code, number)

    # 4️⃣ Ask Scryfall for the official name
    card_json = fetch_card(set_code, number)
    name = extract_name(card_json)

    if name:
        log.info("Scryfall result → %s", name)
    else:
        log.warning(
            "Scryfall did not return a name for %s #%s",
            set_code,
            number,
        )
    return name
