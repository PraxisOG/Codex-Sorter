import cv2
import numpy as np
import pytesseract
import re
import requests
from ..config import OCR_WHITELIST, SCRYFALL_CARD_URL
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------
# Low‑level helpers (unchanged logic, just moved into a class for reuse)
# ----------------------------------------------------------------------
def mini_ocr(image: np.ndarray) -> str:
    """Run the light pre‑processing you already wrote and return raw OCR text."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    processed = cv2.bitwise_not(gray)

    # optional debugging image – keep it if you like
    cv2.imwrite("def_mini_ocr.png", processed)

    cfg = f"-c tessedit_char_whitelist={OCR_WHITELIST} --psm 4"
    text = pytesseract.image_to_string(processed, config=cfg)
    return text.strip()


# ----------------------------------------------------------------------
# Extraction helpers (number / set code)
# ----------------------------------------------------------------------
def number_extraction(txt: str) -> str:
    """Return only the numeric collector number from a raw OCR line."""
    if '/' in txt:
        txt = txt.split('/')[0]

    digits = [ch for ch in txt if ch.isdigit()]

    # Some cards have a leading zero that you want to drop when 4 digits are found
    if len(digits) == 4:
        digits = digits[1:]

    return ''.join(digits)


def set_extraction(txt: str) -> str:
    """First three characters of the line – usually the set code."""
    return txt[:3].upper()


def get_line(text: str, line_num: int) -> str:
    """
    Return a logical line relative to the first line that contains at least
    three digits (the collector‑number line).  If such a line cannot be found,
    fall back to the raw index.
    """
    lines = text.splitlines()
    digit_pattern = re.compile(r'\d')
    numeric_line_idx = None

    for i, line in enumerate(lines):
        if sum(1 for _ in digit_pattern.finditer(line)) >= 3:
            numeric_line_idx = i
            break

    if numeric_line_idx is None:
        return lines[line_num] if 0 <= line_num < len(lines) else ""

    target_idx = numeric_line_idx + line_num
    return lines[target_idx] if 0 <= target_idx < len(lines) else ""


# ----------------------------------------------------------------------
# Scryfall helpers (moved from the original script)
# ----------------------------------------------------------------------
def fetch_card(set_code: str, collector_number: str) -> dict | None:
    """Query Scryfall – returns JSON or None on error/404."""
    url = SCRYFALL_CARD_URL.format(
        set_code=set_code.lower(),
        collector_number=collector_number,
    )
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        log.warning(f"No card found for {set_code.upper()} #{collector_number}")
        return None
    except Exception as exc:
        log.error(f"Scryfall request failed: {exc}")
        return None


def extract_name(card_data: dict) -> str:
    """Pull the official name field from a Scryfall JSON payload."""
    if not card_data:
        return ""
    return card_data.get("name", "")


# ----------------------------------------------------------------------
# High‑level convenience function (what your original `img_to_name` did)
# ----------------------------------------------------------------------
def img_to_name(image: np.ndarray) -> str:
    """
    Full pipeline:

      1. OCR raw text
      2. Pull the collector number & set code from the appropriate lines
      3. Query Scryfall
      4. Return the card name (or empty string on failure)
    """
    full_text = mini_ocr(image)
    log.debug(f"OCR raw output:\n{full_text}")

    number   = number_extraction(get_line(full_text, 0))
    set_code = set_extraction(get_line(full_text, 1))

    log.info(f"Parsed → Set: {set_code}, Number: {number}")

    card_json = fetch_card(set_code, number)
    name = extract_name(card_json) if card_json else ""
    log.info(f"Scryfall result → {name}")
    return name


# ----------------------------------------------------------------------
# Pre‑processing helpers (rotate / crop – unchanged from your script)
# ----------------------------------------------------------------------
def rotate_image(img: np.ndarray,
                 angle_deg: float,
                 keep_size: bool = False) -> np.ndarray:
    h, w = img.shape[:2]
    centre = (w // 2, h // 2)

    rot_mat = cv2.getRotationMatrix2D(centre, angle_deg, scale=1.0)

    if keep_size:
        rotated = cv2.warpAffine(img, rot_mat, (w, h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    else:
        cos = np.abs(rot_mat[0, 0])
        sin = np.abs(rot_mat[0, 1])

        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)

        rot_mat[0, 2] += (new_w / 2) - centre[0]
        rot_mat[1, 2] += (new_h / 2) - centre[1]

        rotated = cv2.warpAffine(img, rot_mat, (new_w, new_h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    return rotated


def crop_image(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    img_h, img_w = img.shape[:2]

    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))

    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))

    return img[y:y + h, x:x + w]


def preprocessing(image_input: np.ndarray) -> np.ndarray:
    """Rotate → crop – exactly the same steps you used before."""
    rotated = rotate_image(image_input, 180)
    cropped  = crop_image(rotated, 200, 370, 800, 90)
    return cropped