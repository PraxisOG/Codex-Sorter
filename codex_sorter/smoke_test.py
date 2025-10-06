#!/usr/bin/env python3
import time
from codex_sorter.libraries.printer.xl_kinematics import (
    make_octoprint_client, home_all_axes, move_head, drop_card,
)
from codex_sorter.libraries.hardware.toolhead import Fan, CardDetect
from codex_sorter.libraries.config import OCTOPRINT_URL,OCTOPRINT_APIKEY

client = make_octoprint_client(
    OCTOPRINT_URL,
    OCTOPRINT_APIKEY
)

fan   = Fan(client)
button = CardDetect(client)

print("Homing…")
home_all_axes(client)
time.sleep(2)

print("Moving +10 mm on X")
move_head(client, x=10)           # relative jog
time.sleep(1)

print("Turning fan ON for 5 s")
fan.on()
time.sleep(5)
fan.off()

print("All good – now you can run `main.py`")
