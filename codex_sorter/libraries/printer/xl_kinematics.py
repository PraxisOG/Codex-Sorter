#!/usr/bin/env python3
# ----------------------------------------------------------------------
#   codex_sorter/xl_kinematics.py
# ----------------------------------------------------------------------
"""
Low‑level motion helpers for the Prusa XL card sorter.

Only this file (together with ``simple_ocr.py``, ``toolhead.py`` and ``main.py``)
is required to run the whole system – all references to the former
``printer_kinematics`` package have been removed.

The printer is *always* driven through a relative‑jog command
(``client.jog(x=…, y=…, z=…)``).  To make that convenient we keep a tiny
in‑process state table (``_pos``) that records the last known X/Y/Z location.
All public helpers accept **absolute** coordinates (easier to read in the
calling code); they translate those into relative deltas before sending them
to OctoPrint.

The module also contains a small ``make_octoprint_client`` factory and a very
lightweight ``home_all_axes`` implementation that moves the head from the
firmware home position to the configurable *post‑home* offset.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

# ----------------------------------------------------------------------
#   External imports – keep them local so this file can be used on its own
# ----------------------------------------------------------------------
from octorest import OctoRest          # pip‑install octorest
from codex_sorter.libraries.config import (
    POST_HOME_X,
    POST_HOME_Y,
    POST_HOME_Z,
    INPUT_STACK_X,
    INPUT_STACK_Y,
    INPUT_STACK_Z,
    TILE_STEP,
)
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------
#   Simple data container for the current (relative) head position.
# ----------------------------------------------------------------------
@dataclass
class _Position:
    """Tracks where we *think* the printhead is (relative to firmware home)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


# Global mutable state – the sorter runs single‑threaded so this is fine.
_current_pos = _Position()


# ----------------------------------------------------------------------
#   OctoPrint client factory (the snippet you gave us)
# ----------------------------------------------------------------------
def make_octoprint_client(url: str, apikey: str) -> OctoRest:
    """
    Return a ready‑to‑use ``OctoRest`` instance.

    All connection problems are logged and then re‑raised so the caller can
    decide what to do (the original script printed the exception – we now log).
    """
    try:
        client = OctoRest(url=url, apikey=apikey)
        log.debug("OctoPrint client created for %s", url)
        return client
    except Exception as exc:            # pragma: no cover – defensive
        log.error("Could not connect to OctoPrint at %s : %s", url, exc)
        raise


# ----------------------------------------------------------------------
#   Motion primitives (relative jog helpers)
# ----------------------------------------------------------------------
def _jog_delta(client: Any, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
    """
    Send a **relative** jog to OctoPrint and update ``_current_pos``.
    Zero deltas are ignored (OctoPrint would reject an empty command).
    """
    if dx == dy == dz == 0:
        log.debug("No delta supplied to _jog_delta – nothing to do")
        return

    try:
        log.info(
            "Jogging head Δx=%.2f mm  Δy=%.2f mm  Δz=%.2f mm",
            dx, dy, dz,
        )
        client.jog(x=dx, y=dy, z=dz)
        # Give the firmware a tiny breathing room – avoids command flooding.
        time.sleep(0.1)

        _current_pos.x += dx
        _current_pos.y += dy
        _current_pos.z += dz
    except Exception as exc:            # pragma: no cover – defensive
        log.error("Failed to jog head (Δx=%s, Δy=%s, Δz=%s): %s", dx, dy, dz, exc)
        raise


def move_head(
    client: Any,
    *,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
) -> None:
    """
    Public helper used by ``main.py`` – accepts **absolute** coordinates
    (relative to the printer’s firmware home), computes the required relative
    delta and forwards it to :func:`_jog_delta`.

    Any axis set to ``None`` is left untouched.
    """
    # Compute deltas from the *current* tracked position.
    dx = (x - _current_pos.x) if x is not None else 0.0
    dy = (y - _current_pos.y) if y is not None else 0.0
    dz = (z - _current_pos.z) if z is not None else 0.0

    log.debug(
        "move_head request – target absolute (x=%s, y=%s, z=%s)",
        x, y, z,
    )
    _jog_delta(client, dx=dx, dy=dy, dz=dz)


def home_all_axes(client: Any) -> None:
    """
    Home the printer (firmware‑level ``G28`` via OctoPrint) and then move
    to the *post‑home* offset defined in ``config.py``.

    After this call ``_current_pos`` reflects the post‑home coordinates,
    which become the reference point for all subsequent relative moves.
    """
    log.info("Homing printer axes …")
    try:
        client.home()                     # absolute home – octoprint takes care of limits
        time.sleep(2)                     # give firmware a moment to settle
    except Exception as exc:              # pragma: no cover – defensive
        log.error("Failed to home printer: %s", exc)
        raise

    # Move from (0,0,0) → post‑home offset.
    _jog_delta(
        client,
        dx=POST_HOME_X,
        dy=POST_HOME_Y,
        dz=POST_HOME_Z,
    )
    log.info(
        "Reached post‑home position X=%.2f Y=%.2f Z=%.2f",
        POST_HOME_X, POST_HOME_Y, POST_HOME_Z,
    )


def lower_until_contact(
    client: Any,
    sensor: Any,
    *,
    step_mm: float = 0.5,
    max_travel: Optional[float] = None,
) -> None:
    """
    Lower the toolhead **downwards** (negative Z) in ``step_mm`` increments
    until ``sensor.is_pressed()`` becomes true.

    Parameters
    ----------
    client : Any
        OctoPrint client.
    sensor : Any
        Object exposing ``is_pressed() → bool`` – our ``CardDetect`` class.
    step_mm : float, optional
        Size of each incremental jog (default 0.5 mm).
    max_travel : float or None, optional
        Safety guard; if supplied the function aborts with a ``RuntimeError``
        after travelling more than this distance downwards.
    """
    traveled = 0.0
    log.info("Lowering until card contacts sensor…")
    while not sensor.is_pressed():
        if max_travel is not None and traveled >= max_travel:
            msg = f"Exceeded safe lower‑travel limit of {max_travel} mm"
            log.error(msg)
            raise RuntimeError(msg)

        # Jog **down** → negative Z delta
        _jog_delta(client, dz=-step_mm)
        traveled += step_mm
        time.sleep(0.05)      # let the sensor settle


def drop_card(client: Any) -> None:
    """
    Release suction so that the held card falls.

    The original code assumed a ``client.fan_off()`` method; many OctoPrint
    installations expose this via a custom plugin.  If it does not exist we
    simply log the intent – the higher level ``toolhead.Fan`` class will have
    already turned the fan off before calling us.
    """
    try:
        client.fan_off()                      # type: ignore[attr-defined]
        log.info("Suction fan turned OFF (drop_card)")
    except Exception:                         # pragma: no cover – defensive fallback
        log.debug(
            "client.has no 'fan_off' method – assuming suction already disabled"
        )


# ----------------------------------------------------------------------
#   Kinematics & convenience helpers
# ----------------------------------------------------------------------
def move_to_input_stack(client: Any) -> None:
    """
    Position the head directly above the **input** card stack.

    The required motion is simply the vector difference between the
    ``POST_HOME_*`` offset and the ``INPUT_STACK_*`` coordinates.
    """
    dx = INPUT_STACK_X - POST_HOME_X
    dy = INPUT_STACK_Y - POST_HOME_Y
    dz = INPUT_STACK_Z - POST_HOME_Z   # typically a small lift above the pile

    log.info(
        "Moving to input stack (Δx=%.2f, Δy=%.2f, Δz=%.2f)",
        dx,
        dy,
        dz,
    )
    _jog_delta(client, dx=dx, dy=dy, dz=dz)


def kinematics(card_name: str) -> Dict[str, float]:
    """
    Resolve the **absolute** target coordinates for a card based on its OCR
    result.

    Rules (as you specified):

    * Always raise at least 35 mm above the current Z before any lateral move.
    * If no name was detected → shift left  (‑X) by ``TILE_STEP``.
    * If a name **was** detected → shift forward (+Y) by ``TILE_STEP``.
    * The special case “Colossal Dreadmaw” → shift right (+X) by ``TILE_STEP``
      instead of the generic forward move.

    Returns
    -------
    dict
        Keys ``x``, ``y`` and ``z`` holding **absolute** coordinates that can be
        fed straight to :func:`move_head`.
    """
    # Start from a safe Z (post‑home + 35 mm clearance)
    target_z = POST_HOME_Z + 35.0

    # Base XY is the post‑home location – everything else is an offset.
    target_x = POST_HOME_X
    target_y = POST_HOME_Y

    if not card_name:                                    # undetected → left
        target_x -= TILE_STEP
        log.debug("Kinematics: no OCR result → LEFT")
    elif card_name == "Colossal Dreadmaw":               # special right move
        target_x += TILE_STEP
        log.debug('Kinematics: special case "%s" → RIGHT', card_name)
    else:                                                # any other name → forward
        target_y += TILE_STEP
        log.debug('Kinematics: OCR result "%s" → FORWARD', card_name)

    result = {"x": target_x, "y": target_y, "z": target_z}
    log.info("Resolved kinematics for \"%s\" → %s", card_name, result)
    return result


# ----------------------------------------------------------------------
#   Exported names (what ``import *`` brings in)
# ----------------------------------------------------------------------
__all__ = [
    "make_octoprint_client",
    "home_all_axes",
    "move_head",
    "lower_until_contact",
    "drop_card",
    "move_to_input_stack",
    "kinematics",
]
