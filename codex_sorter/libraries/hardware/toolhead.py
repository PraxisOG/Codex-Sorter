# ----------------------------------------------------------------------
#   codex_sorter/libraries/hardware/toolhead.py
# ----------------------------------------------------------------------
"""
Tool‑head helpers for the card‑sorting robot.

* ``capture_image_at_focus`` – grabs a single, well‑focused frame from the
  webcam.  All camera handling (open/close, autofocus toggle, focus set,
  warm‑up frames) lives here and is fully logged.
* ``Fan`` – thin wrapper around a ``gpiozero.Motor`` that supplies suction.
  The wrapper automatically inserts a one‑second delay when turning on or
  off so the fan has time to spool up / despool.
* ``CardDetect`` – debounced button (GPIO) that reports whether a card is
  currently under the head.  Provides both ``is_pressed()`` (the API used by
  ``main.wait_for_button``) and ``wait_for_press()`` for explicit waiting.

All side‑effects are logged via the project's central logger.
"""

from __future__ import annotations

import time
from typing import Optional

import cv2
from gpiozero import Button, Motor

# ----------------------------------------------------------------------
#   Local imports – keep the absolute import style used elsewhere
# ----------------------------------------------------------------------
from ..config import (
    CAMERA_INDEX,
    FOCUS_VALUE,
    FAN_PIN_ONE,
    BUTTON_PIN,
)
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------
#   Camera helper
# ----------------------------------------------------------------------
def capture_image_at_focus(
    cam_index: int = CAMERA_INDEX,
    focus: int = FOCUS_VALUE,
    autofocus_off: bool = True,
    warmup_frames: int = 10,
    wait_after_focus_ms: int = 200,
) -> Optional[cv2.typing.MatLike]:
    """
    Grab a single frame from the webcam with an explicit manual focus.

    Parameters
    ----------
    cam_index : int, optional
        Index of the camera device (default taken from ``config``).
    focus : int, optional
        Integer value sent to ``CAP_PROP_FOCUS``.  Ignored if the driver does not
        expose the property.
    autofocus_off : bool, optional
        If *True* we try to disable auto‑focus before setting the manual value.
    warmup_frames : int, optional
        Number of frames read and discarded after opening the device – this
        clears any exposure/white‑balance settling time.
    wait_after_focus_ms : int, optional
        Small pause after setting focus so the lens can settle.

    Returns
    -------
    cv2.typing.MatLike or None
        The captured image (BGR ndarray) on success, ``None`` otherwise.
    """
    log.debug(
        "Opening camera %s (autofocus_off=%s, focus=%s)",
        cam_index,
        autofocus_off,
        focus,
    )
    # NOTE: On Windows the DSHOW backend is required; on Linux the default
    #       works fine.  The conditional keeps the code portable.
    cap = cv2.VideoCapture(
        cam_index,
        cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0,
    )

    if not cap.isOpened():
        log.error("Cannot open camera %s", cam_index)
        return None

    try:
        # --------------------------------------------------------------
        # 1️⃣ Auto‑focus handling
        # --------------------------------------------------------------
        if autofocus_off:
            ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)  # 0 → off
            if not ok:
                log.warning("Camera does not expose CAP_PROP_AUTOFOCUS")
            else:
                log.debug("Auto‑focus disabled")

        # --------------------------------------------------------------
        # 2️⃣ Manual focus value (if supported)
        # --------------------------------------------------------------
        ok_focus = cap.set(cv2.CAP_PROP_FOCUS, float(focus))
        if not ok_focus:
            log.warning(
                "Camera does not expose CAP_PROP_FOCUS – ignoring focus value"
            )
        else:
            log.debug("Manual focus set to %s", focus)

        # --------------------------------------------------------------
        # 3️⃣ Warm‑up frames (throw away)
        # --------------------------------------------------------------
        for i in range(warmup_frames):
            ret, _ = cap.read()
            if not ret:
                log.warning(
                    "Warm‑up frame %d failed – continuing anyway", i + 1
                )
                break

        # --------------------------------------------------------------
        # 4️⃣ Allow the lens to settle (ms → seconds)
        # --------------------------------------------------------------
        if wait_after_focus_ms > 0:
            time.sleep(wait_after_focus_ms / 1000.0)

        # --------------------------------------------------------------
        # 5️⃣ Capture the actual image
        # --------------------------------------------------------------
        ret, frame = cap.read()
        if not ret:
            log.error("Failed to capture a frame after warm‑up")
            return None

        log.info(
            "Image captured (shape=%s, dtype=%s)", frame.shape, frame.dtype
        )
        return frame

    finally:
        # Ensure the device is always released – even on exceptions.
        cap.release()
        cv2.destroyAllWindows()


# ----------------------------------------------------------------------
#   Fan / suction motor
# ----------------------------------------------------------------------
class Fan:
    """
    Wrapper around a ``gpiozero.Motor`` that drives the suction fan.

    The motor runs only in one direction (forward).  Turning the fan *on*
    inserts a 1 s delay to let it spool up, and turning it *off* does the
    same for a clean release of the card.
    """

    _SPINUP_TIME = 1.0   # seconds – adjust if you find a different value works better

    def __init__(self, pin: int = FAN_PIN_ONE):
        """
        Parameters
        ----------
        pin : int, optional
            GPIO BCM pin that controls the fan (default from ``config``).
        """
        self.motor = Motor(forward=pin)
        log.debug("Fan motor initialised on GPIO %s", pin)

    def on(self) -> None:
        """Start suction and wait for it to reach full speed."""
        log.info("Turning fan ON – spin‑up")
        self.motor.forward()
        time.sleep(self._SPINUP_TIME)
        log.debug("Fan is now at full speed")

    def off(self) -> None:
        """Stop suction after a short delay (allows the card to release)."""
        log.info("Turning fan OFF – spin‑down")
        # ``Motor.stop`` immediately cuts power; we keep the motor running for
        # a second so any residual suction can let go of the card.
        self.motor.stop()
        time.sleep(self._SPINUP_TIME)
        log.debug("Fan fully stopped")

    def __del__(self):
        """Safety net – make sure the GPIO is cleaned up on interpreter exit."""
        try:
            self.off()
            self.motor.close()
            log.debug("Fan resources released")
        except Exception:   # pragma: no cover – defensive only
            pass


# ----------------------------------------------------------------------
#   Card‑detect button (debounced)
# ----------------------------------------------------------------------
class CardDetect:
    """
    Simple wrapper for a debounced GPIO button that signals when a card is
    physically under the suction head.

    The class mirrors the API used in ``main.wait_for_button`` (`is_pressed`)
    and also exposes the convenience method ``wait_for_press``.
    """

    def __init__(self, pin: int = BUTTON_PIN, bounce_time: float = 0.1):
        """
        Parameters
        ----------
        pin : int, optional
            GPIO BCM pin connected to the button (default from ``config``).
        bounce_time : float, optional
            Debounce interval in seconds.
        """
        self._button = Button(pin, bounce_time=bounce_time)
        log.debug(
            "CardDetect button initialised on GPIO %s (bounce_time=%ss)",
            pin,
            bounce_time,
        )

    # ------------------------------------------------------------------
    # Compatibility helpers used by the rest of the codebase
    # ------------------------------------------------------------------
    def is_pressed(self) -> bool:
        """
        Return ``True`` if the sensor / button reports a pressed state.

        This non‑blocking call is what ``main.wait_for_button`` polls.
        """
        state = self._button.is_pressed
        log.debug("CardDetect.is_pressed → %s", state)
        return state

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        """
        Block until the button is pressed or *timeout* seconds elapse.

        Returns ``True`` if the press happened, ``False`` on timeout.
        """
        log.info(
            "Waiting for card‑detect press (timeout=%s)", str(timeout)
        )
        result = self._button.wait_for_press(timeout=timeout)
        if result:
            log.info("Card‑detect button pressed")
        else:
            log.warning("Timeout waiting for card‑detect press")
        return result

    # ------------------------------------------------------------------
    # Clean‑up – ``gpiozero`` automatically releases pins on program exit,
    # but we provide a deterministic close just in case.
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Explicitly release the underlying GPIO resources."""
        try:
            self._button.close()
            log.debug("CardDetect button resources released")
        except Exception:   # pragma: no cover – defensive only
            pass

    def __del__(self):
        self.close()


# ----------------------------------------------------------------------
#   Public symbols that other modules expect to import directly
# ----------------------------------------------------------------------
__all__ = [
    "capture_image_at_focus",
    "Fan",
    "CardDetect",
]
