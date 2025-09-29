import cv2
import numpy as np
import pytesseract
import requests
import time
import re

#Settings
SCRYFALL_CARD_URL = "https://api.scryfall.com/cards/{set_code}/{collector_number}"

# Lightweight OCR Script with light processing
def mini_ocr(image: np.ndarray):
    # Setting the image
    crop = image

    # ---- force grayscale before inversion (prevents colour tint)
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # invert the binary image
    processed = cv2.bitwise_not(crop_gray)

    # optional: write the pre‑processed patch for visual debugging
    cv2.imwrite("def_mini_ocr.png", processed)

    # whitelist only characters we expect in set/collector numbers
    whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-\\/ "
    cfg = f"-c tessedit_char_whitelist={whitelist} --psm 4"

    # Convert and return image
    text = pytesseract.image_to_string(processed, config=cfg)
    return text.strip()          # remove leading/trailing whitespace

# Extracts the number
def number_extraction(txt) -> str:
    # Keep everything left of the first slash (if any)
    if '/' in txt:
        txt = txt.split('/')[0]          # e.g. "129/249R" → "129"

    # Build a new string containing only digit characters
    digits: list[str] = []               # temporary list to collect chars
    for ch in txt:                       # walk through each character
        if '0' <= ch <= '9':              # is it a digit?
            digits.append(ch)             # keep it

    # Get rid of the first number if there are four
    if len(digits) == 4:
        digits = digits[1:]

    # Join the collected characters back into one string
    return ''.join(digits)

# Returns the first 3 characters of a given line, which extracts the set code of newer mtg cards
def set_extraction(txt) -> str:
    # Slice the string; if it’s shorter than 3 chars we just return whatever is there
    return txt[:3]

# Returns the line specified on a newer magic card, includes character rejection
def get_line(text: str, line_num: int) -> str:
    """
    Return the requested line *after* re‑indexing so that the first line
    containing three or more digits becomes logical line 0.

    Parameters
    ----------
    text : str
        The whole input string (may contain new‑lines).
    line_num : int
        Zero‑based index you want, counted from the numeric line.

    Returns
    -------
    str
        The requested line, or an empty string if the index is out of range.
    """
    # Split the raw text into its physical lines
    lines = text.splitlines()

    # Find the first line that has at least three digits (0‑9)
    numeric_line_idx = None
    digit_pattern = re.compile(r'\d')          # matches a single digit

    for i, line in enumerate(lines):
        # Count how many digit characters are present in this line
        if sum(1 for _ in digit_pattern.finditer(line)) >= 3:
            numeric_line_idx = i
            break

    # If we never found such a line, fall back to the original behaviour
    if numeric_line_idx is None:
        return lines[line_num] if 0 <= line_num < len(lines) else ""

    # Compute the “logical” index that the caller asked for
    target_idx = numeric_line_idx + line_num

    # Return the appropriate line, or an empty string if out‑of‑range
    return lines[target_idx] if 0 <= target_idx < len(lines) else ""

# Queries Scryfall with set code and collector number and returns a card name
def fetch_card(set_code: str, collector_number: str) -> dict | None:
    """
    Query Scryfall for a single card given its set code and collector number.

    Parameters
    ----------
    set_code : str
        The three‑letter (or numeric) set code – e.g. "mh3".
    collector_number : str
        The numeric part of the collector number – e.g. "0202".

    Returns
    -------
    dict | None
        The JSON payload for the card if the request succeeded,
        otherwise ``None`` (e.g. 404 → card not found).
    """
    url = SCRYFALL_CARD_URL.format(
        set_code=set_code.lower(),          # Scryfall expects lower‑case codes
        collector_number=collector_number
    )
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        else:
            # 404 means “no card with that number in that set”
            print(f"⚠️ No card found for {set_code.upper()} #{collector_number}")
            return None
    except requests.RequestException as e:
        print(f"❌ Request error: {e}")
        return None

# Extracts the name of a given MTG card from the JSON returned from the Scryfall API
def extract_name(card_data: dict) -> str:
    """
    Return the printable name of a Scryfall card object.

    Parameters
    ----------
    card_data : dict
        The JSON dictionary you get back from the Scryfall API (e.g. the
        huge example you posted).

    Returns
    -------
    str
        The value of the top‑level ``"name"`` field, or an empty string if the
        key is missing.
    """
    # The official field that holds the card’s name is simply "name".
    try:
        return card_data.get("name", "")
    except:
        return None

# Takes an image and returns the name of an MTG card if detected
def img_to_name(image_input):
    full_text = mini_ocr(image_input)
    print("fulltext:" + full_text)

    number = number_extraction(get_line(full_text,0))
    set_code = set_extraction(get_line(full_text,1))

    print("number: " + number)
    print("set_code: " + set_code)

    card_data = fetch_card(set_code, number)
    card_name =  extract_name(card_data)

    print(card_name)

# Performs processing on the image before OCR
def preprocessing(image_input):
    # Corrects rotation
    rotated = rotate_image(image_input,180)
    # crops for OCR
    cropped = crop_image(rotated,200,370,800,90)
    
    return cropped

# Rotates an input image by a given amount
def rotate_image(img: np.ndarray,
                 angle_deg: float,
                 keep_size: bool = False) -> np.ndarray:
    """
    Rotate an image around its centre.

    Parameters
    ----------
    img : np.ndarray
        Input image (any format OpenCV can read).
    angle_deg : float
        Rotation angle in **degrees**.
        Positive → counter‑clockwise, negative → clockwise.
    keep_size : bool, optional
        If ``True`` the output is forced to have the same width/height as the
        input (the image will be cropped).  Default ``False`` returns the full
        rotated canvas so nothing gets cut off.

    Returns
    -------
    np.ndarray
        The rotated image.
    """
    h, w = img.shape[:2]
    centre = (w // 2, h // 2)

    # Rotation matrix (scale=1 → no zoom)
    rot_mat = cv2.getRotationMatrix2D(centre, angle_deg, scale=1.0)

    if keep_size:
        # Keep original dimensions – the image may be clipped at the borders.
        rotated = cv2.warpAffine(img, rot_mat, (w, h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    else:
        # Expand canvas so the whole rotated picture fits.
        cos = np.abs(rot_mat[0, 0])
        sin = np.abs(rot_mat[0, 1])

        new_w = int(h * sin + w * cos)
        new_h = int(h * cos + w * sin)

        # Adjust the rotation matrix to translate the image to the centre
        rot_mat[0, 2] += (new_w / 2) - centre[0]
        rot_mat[1, 2] += (new_h / 2) - centre[1]

        rotated = cv2.warpAffine(img, rot_mat, (new_w, new_h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)

    return rotated

# Crops an input image by a given amount
def crop_image(img: np.ndarray,
               x: int,
               y: int,
               w: int,
               h: int) -> np.ndarray:
    """
    Crop a rectangular region from an image.

    Parameters
    ----------
    img : np.ndarray
        Input image (BGR, Gray … – any format OpenCV can read).
    x, y : int
        Top‑left corner of the crop rectangle.
    w, h : int
        Width and height of the crop rectangle.

    Returns
    -------
    np.ndarray
        The cropped image patch.
    """
    # --------------------------------------------------------------
    # Clamp the requested region so it stays inside the original image.
    img_h, img_w = img.shape[:2]

    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))

    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))

    # --------------------------------------------------------------
    # Slice out the region.
    cropped = img[y:y + h, x:x + w]
    return cropped

# Captures a webcam image with the specified amount of focus
def capture_image_at_focus(
    cam_index: int = 0,
    focus: int = 100,
    autofocus_off: bool = True,
    warmup_frames: int = 10,
    wait_after_focus_ms: int = 200,
) -> np.ndarray | None:
    """
    Grab one frame from a webcam using a manual focus value.

    Parameters
    ----------
    cam_index : int, default 0
        Index of the camera.
    focus : int, default 100
        Desired focus position (usually 0‑255, but check your device).
    autofocus_off : bool, default True
        Try to disable auto‑focus before setting a manual value.
    warmup_frames : int, default 10
        Number of frames to discard after opening the camera – lets the
        sensor and driver settle.
    wait_after_focus_ms : int, default 200
        Extra pause (in ms) after writing the focus property so the lens has
        time to move before we capture.

    Returns
    -------
    np.ndarray | None
        Captured BGR image or ``None`` if a frame could not be read.
    """
    # --------------------------------------------------------------
    # 1️⃣ Open camera – use DirectShow on Windows for maximum control.
    cap = cv2.VideoCapture(
        cam_index,
        cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0,
    )
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera with index {cam_index}")

    # --------------------------------------------------------------
    # 2️⃣ (Optional) turn auto‑focus off.
    if autofocus_off:
        ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        if not ok:
            print("[WARN] Camera does not expose CAP_PROP_AUTOFOCUS")

    # --------------------------------------------------------------
    # 3️⃣ Set manual focus – check the return value.
    ok_focus = cap.set(cv2.CAP_PROP_FOCUS, float(focus))
    if not ok_focus:
        print("[WARN] Camera does not expose CAP_PROP_FOCUS – "
              "focus may be ignored or out of range")

    # --------------------------------------------------------------
    # 4️⃣ Warm‑up: read a few frames and discard them.
    for _ in range(warmup_frames):
        ret, _ = cap.read()
        if not ret:
            print("[WARN] Frame read failed during warm‑up")
            break

    # Give the lens a moment to move after we set the focus value.
    cv2.waitKey(wait_after_focus_ms)

    # --------------------------------------------------------------
    # 5️⃣ Capture the actual frame.
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Could not read a frame after warm‑up")
        frame = None

    # --------------------------------------------------------------
    # 6️⃣ Clean up.
    cap.release()
    cv2.destroyAllWindows()

    return frame

def main():
    capture = capture_image_at_focus(focus=200)
    processed_image = preprocessing(capture)
    name = img_to_name(processed_image)
    print(name)

if __name__ == "__main__":
    main()