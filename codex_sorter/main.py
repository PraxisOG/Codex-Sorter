#!/usr/bin/env python3
# codex_sorter/main.py
import sys
from pathlib import Path
import time

# ----------------------------------------------------------------------
# Add project root to PYTHONPATH (your existing boiler‑plate)
# ----------------------------------------------------------------------
root_dir = str(Path(__file__).parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

# ----------------------------------------------------------------------
# Imports – keep the ones you already use
# ----------------------------------------------------------------------
from .libraries.logger import get_logger
from .libraries.hardware.printer import (
    make_octoprint_client,   # returns an OctoPrint API wrapper
    home_all_axes,           # homes X/Y/Z
    Fan,                     # fan control class
    CardDetect,              # button / sensor for “card present”
    CaptureLED,              # LED that lights the camera
)
from .libraries.hardware.toolhead import capture_image_at_focus
from .libraries.ocr.simple_ocr import preprocessing, img_to_name

log = get_logger(__name__)

# ----------------------------------------------------------------------
# Helper utilities (pseudo‑implementations – replace with your real code)
# ----------------------------------------------------------------------
def wait_for_button(sensor: CardDetect, description: str = "") -> None:
    """
    Block until the supplied sensor goes HIGH / is pressed.
    """
    log.info(f"Waiting for button press… {description}")
    while not sensor.is_pressed():
        time.sleep(0.05)          # poll 20 Hz – adjust as needed
    log.info("Button pressed!")

def move_head(client, x=None, y=None, z=None, feedrate=3000):
    """
    Wrapper around the OctoPrint G‑code API.
    Only the axes you pass are moved; others stay where they are.
    """
    cmd = "G1"
    if x is not None:  cmd += f" X{x}"
    if y is not None:  cmd += f" Y{y}"
    if z is not None:  cmd += f" Z{z}"
    cmd += f" F{feedrate}"
    client.send_gcode(cmd)

def lower_until_contact(client, sensor: CardDetect, step_mm=1.0):
    """
    Lower the Z‑axis in `step_mm` increments until the sensor is triggered.
    Returns the final Z position (you can keep track of it yourself if you need).
    """
    while not sensor.is_pressed():
        # move down by one step
        client.send_gcode(f"G91")                     # relative positioning
        client.send_gcode(f"G1 Z-{step_mm} F1500")
        client.send_gcode(f"G90")                     # back to absolute
        time.sleep(0.2)                               # give the machine a moment
    log.info("Contact detected – card is at the tip of the toolhead.")
    # you could query the current position here if needed:
    # pos = client.get_current_position()
    # return pos['z']

def run_ocr_and_get_type():
    """
    Capture an image, preprocess it and feed it to the OCR routine.
    Returns a string that identifies the card type (e.g., "A", "B", …).
    """
    img = capture_image_at_focus()                     # from toolhead lib
    prepped = preprocessing(img)
    name = img_to_name(prepped)                        # simple_ocr returns a label
    log.info(f"OCR identified card as: {name}")
    return name

def kinematics(card_type):
    """
    Very small, hard‑coded lookup that translates a card type into a drop location.
    In real life you might compute X/Y/Z based on geometry; here we just map.
    Returns a dict with target coordinates.
    """
    # Example layout – adjust to match your physical sorter
    mapping = {
        "A": {"x": 150, "y":   0, "z": 10},
        "B": {"x": 150, "y":  20, "z": 10},
        "C": {"x": 150, "y":  40, "z": 10},
        # default/fallback
        "UNKNOWN": {"x": 150, "y": -20, "z": 10},
    }
    return mapping.get(card_type.upper(), mapping["UNKNOWN"])

def drop_card(client):
    """
    Open the suction (or turn off fan) and raise a tiny bit so the card releases.
    Adjust to whatever mechanism you actually use.
    """
    # Example: turn fan OFF → negative pressure stops, gravity drops the card
    client.fan_off()               # if your Fan class has this method
    time.sleep(0.3)                # give the suction a moment to release
    move_head(client, z=5)         # lift slightly (optional)

# ----------------------------------------------------------------------
# Main routine 
# ----------------------------------------------------------------------
def main(iterations: int = 10) -> None:
    """
    Run the whole sorting cycle `iterations` times.
    """
    log.info("=== STARTING CARD‑SORTER ===")

    # --------------------------------------------------------------
    # 1️⃣ Connect to the printer (OctoPrint client)
    # --------------------------------------------------------------
    client = make_octoprint_client()          # <-- returns a wrapper object
    fan     = Fan(client)                      # control the suction fan
    button  = CardDetect(client)               # physical “stop‑down” sensor
    led     = CaptureLED(client)               # LED that lights the camera

    # --------------------------------------------------------------
    # 2️⃣ Wait for the *initial* user button press to home the machine
    # --------------------------------------------------------------
    wait_for_button(button, "Ready to start – press once")
    log.info("=== BUTTON PRESS ===")

    # --------------------------------------------------------------
    # 3️⃣ Home all axes (X/Y/Z)
    # --------------------------------------------------------------
    home_all_axes(client)
    log.info("=== HOMING ===")

    # --------------------------------------------------------------
    # 4️⃣ Wait for a second confirmation before moving the head out
    # --------------------------------------------------------------
    wait_for_button(button, "Press again to move toolhead forward & lower bed")
    log.info("=== BUTTON PRESS ===")

    # --------------------------------------------------------------
    # 5️⃣ Move toolhead to the *front* of printer and lower the bed
    # --------------------------------------------------------------
    # (Values are placeholders – replace with your real coordinates)
    FRONT_X = 300          # just past the front edge, enough for the attachment
    BED_DOWN_Z = -60      # how far you want the build plate down
    move_head(client, x=FRONT_X)            # slide forward
    move_head(client, z=BED_DOWN_Z)        # lower bed (negative Z)

    # --------------------------------------------------------------
    # 6️⃣ Wait for user to attach the toolhead (button press)
    # --------------------------------------------------------------
    wait_for_button(button, "Attach toolhead then press button")

    # --------------------------------------------------------------
    # 7️⃣ Main sorting loop – repeat N times
    # --------------------------------------------------------------
    for i in range(iterations):
        log.info(f"--- Cycle {i+1}/{iterations} ---")

        # ---- a) Move to the *input stack* location -----------------
        INPUT_X = 100      # X coordinate of the card pile
        INPUT_Y = 0        # Y (centered)
        SAFE_Z = 20        # travel height above cards
        move_head(client, x=INPUT_X, y=INPUT_Y, z=SAFE_Z)

        # ---- b) Lower until the “stop‑down” button is triggered,
        #          moving 1 mm at a time (step size can be tuned)
        lower_until_contact(client, sensor=button, step_mm=.5)

        # ---- c) Light the camera & run OCR -------------------------
        card_type = run_ocr_and_get_type()


        # ---- d) Compute drop location via kinematics ---------------
        target = kinematics(card_type)
        log.info(f"Target for {card_type}: X={target['x']} Y={target['y']} Z={target['z']}")

        # ---- e) Move to the drop position (keep current Z, then adjust)
        move_head(client, x=target["x"], y=target["y"])
        # optional: lower a bit more if you need to place the card on a tray
        move_head(client, z=target["z"])

        # ---- f) Release the card -----------------------------------
        drop_card(client)

        # ---- g) Return home (ready for next iteration) -------------
        home_all_axes(client)
        log.info("Cycle complete – ready for next card.")

    # --------------------------------------------------------------
    # 8️⃣ All done – tidy up
    # --------------------------------------------------------------
    fan.off()          # make sure the suction fan is stopped
    log.info("=== SORTING RUN FINISHED ===")

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # You can pass a different number of cycles via CLI if you like:
    #   python -m codex_sorter.main 25
    import sys
    try:
        n = int(sys.argv[1])
    except Exception:
        n = 10                     # default loop count
    main(iterations=n)
