#!/usr/bin/env python3
# codex_sorter/main.py

"""
Entry point for the card‑sorting robot.

The flow mirrors what you described:

1. Wait for a button press → home the printer.
2. Second press   → move the toolhead to the front of the machine (for manual
                     attachment of the custom suction head).
3. Third press    → user signals that the toolhead is attached.
4. For each iteration:
       * go above the input stack,
       * lower until the detection button triggers,
       * turn suction on, capture an image and run OCR,
       * retry OCR once if it fails,
       * compute the destination with ``xl_kinematics.kinematics``,
       * move there (with a mandatory 35 mm Z clearance built‑in),
       * release the card,
       * home again for the next cycle.
"""

import sys
import time
from pathlib import Path

# ----------------------------------------------------------------------
# Project‑wide imports
# ----------------------------------------------------------------------
from codex_sorter.libraries.config import OCTOPRINT_URL, OCTOPRINT_APIKEY, SAFE_Z
from .libraries.logger import get_logger

# Motion / hardware helpers
from codex_sorter.libraries.printer.xl_kinematics import (
    make_octoprint_client,
    home_all_axes,
    move_head,
    lower_until_contact,
    drop_card,
    move_to_input_stack,
    kinematics,
)
from codex_sorter.libraries.hardware.toolhead import Fan, CardDetect, capture_image_at_focus
from codex_sorter.libraries.ocr.simple_ocr import img_to_name

log = get_logger(__name__)

# ----------------------------------------------------------------------
# Small utility – wait for a debounced button press (the same helper you used
# before).  Keeps the log output tidy.
# ----------------------------------------------------------------------
def wait_for_button(sensor: CardDetect, description: str = "") -> None:
    """Block until ``sensor.is_pressed()`` becomes True."""
    if description:
        log.info("Waiting for button press… %s", description)
    else:
        log.info("Waiting for button press…")
    while not sensor.is_pressed():
        time.sleep(0.05)          # poll at ~20 Hz
    log.info("Button pressed!")


# ----------------------------------------------------------------------
# Helper – a fixed 8‑second pause between any motion / fan command.
# This satisfies the “unknown move duration” constraint you mentioned.
# ----------------------------------------------------------------------
def _pause(reason: str = "waiting for motion to settle") -> None:
    log.debug("Pausing %s seconds (%s)", 8, reason)
    time.sleep(8)


# ----------------------------------------------------------------------
# OCR wrapper that retries once on failure.
# ----------------------------------------------------------------------
def _ocr_with_retry(image) -> str:
    """
    Run ``img_to_name``; if the result is empty we retry a single time.
    Returns an empty string only after both attempts failed.
    """
    name = img_to_name(image)
    if name:
        return name

    log.warning("OCR returned empty – retrying once")
    _pause("retry OCR")
    # capture another frame (fresh focus may help)
    image2 = capture_image_at_focus()
    return img_to_name(image2)


# ----------------------------------------------------------------------
# Main routine ---------------------------------------------------------
# ----------------------------------------------------------------------
def main(iterations: int = 10) -> None:
    log.info("=== STARTING CARD‑SORTER ===")

    # --------------------------------------------------------------
    # 1️⃣  Build OctoPrint client and initialise hardware objects
    # --------------------------------------------------------------
    client = make_octoprint_client(OCTOPRINT_URL, OCTOPRINT_APIKEY)
    fan = Fan(client)               # suction / pressure fan
    button = CardDetect(client)     # the “card‑present” sensor

    # --------------------------------------------------------------
    # 2️⃣  First user press → HOME the printer (and move to post‑home)
    # --------------------------------------------------------------
    wait_for_button(button, "Press once to HOME the machine")
    home_all_axes(client)
    _pause("after homing")

    # --------------------------------------------------------------
    # 3️⃣  Second press → move the head to the front of the printer so the
    #     user can manually attach the custom suction toolhead.
    # --------------------------------------------------------------
    wait_for_button(button, "Press again to position the toolhead")
    FRONT_X = 300               # tweak for your XL geometry if needed
    BED_DOWN_Z = -60            # negative Z → lower the build plate (manual attachment)
    move_head(client, x=FRONT_X)          # slide forward
    _pause("after moving to front X")
    move_head(client, z=BED_DOWN_Z)      # drop the bed so you can screw the head on
    _pause("after lowering bed")

    # --------------------------------------------------------------
    # 4️⃣  Third press → user signals that the toolhead is attached.
    # --------------------------------------------------------------
    wait_for_button(button, "Attach toolhead and press button")
    log.info("Toolhead confirmed – beginning sorting cycles")

    # --------------------------------------------------------------
    # 5️⃣  Main sorting loop
    # --------------------------------------------------------------
    for i in range(iterations):
        log.info("--- Cycle %d / %d ---", i + 1, iterations)

        # ----- a) Move above the input stack (safe travel height)
        move_to_input_stack(client)               # uses POST_HOME → INPUT_STACK delta
        _pause("after moving to input stack")
        move_head(client, z=SAFE_Z)               # raise to safe Z if needed
        _pause("after setting SAFE_Z")

        # ----- b) Lower until the button (sensor) triggers
        lower_until_contact(client, sensor=button, step_mm=0.5)
        _pause("after contact detection")

        # ----- c) Turn suction on, capture image, run OCR (with one retry)
        fan.on()                                   # 1 s spin‑up is inside Fan class
        _pause("after turning fan ON")
        raw_img = capture_image_at_focus()
        card_name = _ocr_with_retry(raw_img)

        if not card_name:
            log.warning("OCR failed twice – treating as “unknown” card")
        else:
            log.info('OCR identified card as "%s"', card_name)

        # ----- d) Resolve destination coordinates (kinematics adds the 35 mm Z
        #     clearance automatically)
        target = kinematics(card_name)
        log.info("Moving to target %s", target)

        # ----- e) Travel laterally first, then adjust Z to the drop height
        move_head(client, x=target["x"], y=target["y"])
        _pause("after lateral travel")
        move_head(client, z=target["z"])
        _pause("after setting final Z")

        # ----- f) Release the card (fan off happens inside ``drop_card``)
        drop_card(client)          # tells OctoPrint to stop suction
        _pause("after dropping card")

        # ----- g) Home again – gives a clean, repeatable start for the next card
        home_all_axes(client)
        _pause("after homing before next cycle")

    # --------------------------------------------------------------
    # 6️⃣  Clean‑up – turn fan off (extra safety)
    # --------------------------------------------------------------
    fan.off()
    log.info("=== SORTING RUN FINISHED ===")


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    try:
        n = int(sys.argv[1])
    except Exception:               # pragma: no cover – default path
        n = 10
    main(iterations=n)
