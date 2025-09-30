import time
from octorest import OctoRest
from gpiozero import Motor, LED
from codex_sorter.libraries.config import OCTOPRINT_URL, OCTOPRINT_APIKEY, FAN_PIN_ONE, FAN_PIN_TWO, BUTTON_PIN
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

# ----------------------------------------------------------------------
# OctoPrint wrapper – only the bits you need right now.
# ----------------------------------------------------------------------
def make_octoprint_client() -> OctoRest:
    """Create and return a ready‑to‑use OctoRest client."""
    try:
        client = OctoRest(url=OCTOPRINT_URL, apikey=OCTOPRINT_APIKEY)
        log.debug("OctoPrint client created")
        return client
    except Exception as exc:                     # ConnectionError or others
        log.error(f"Could not connect to OctoPrint: {exc}")
        raise

def home_all_axes(client: OctoRest) -> None:
    """Home X/Y/Z – you can extend this with a pause/resume if you wish."""
    log.info("Homing printer axes …")
    client.home()
    time.sleep(2)                               # give the firmware a moment

def move_to_position(client: OctoRest,x,y,z) -> None:
    """Moves the printhead to specified coodinates"""
    client.jog(x=x,y=y,z=z, )


# ----------------------------------------------------------------------
# Simple fan / suction motor (you already used gpiozero Motor)
# ----------------------------------------------------------------------
class Fan:
    """Wraps a Motor that runs the suction/air‑flow fan."""
    def __init__(self, pin: int = FAN_PIN_ONE):
        self.motor = Motor(forward=pin)   # only forward direction needed
        log.debug(f"Fan motor initialised on GPIO {pin}")

    def on(self):  self.motor.forward()
    def off(self): self.motor.stop()


# ----------------------------------------------------------------------
# Card‑detect button + LED helper (the LED is used while taking a picture)
# ----------------------------------------------------------------------
class CardDetect:
    """Debounced button that tells us when a card touches the suction head."""
    def __init__(self, pin: int = BUTTON_PIN):
        from gpiozero import Button
        self.button = Button(pin, bounce_time=0.1)

    def wait_for_press(self, timeout: float | None = 5) -> bool:
        """Block until the button is pressed or timeout (seconds)."""
        return self.button.wait_for_press(timeout)
