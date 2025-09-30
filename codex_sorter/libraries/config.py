# --------------------------------------------------------------
# Centralised constants – edit them once and everything else sees the change.
# --------------------------------------------------------------


# OctoPrint connection
OCTOPRINT_URL = "http://192.168.86.130:5000"
OCTOPRINT_APIKEY = "vXUq-MOmzAclkDo8Eh7dScOVOrrYJMvJMxmdYAfG-p8"

# GPIO pins (BCM numbering)
FAN_PIN_ONE      = 23      # you can reuse the Motor class for suction/fan
FAN_PIN_TWO      = 24
BUTTON_PIN       = 12      # button that tells you a card is under the head

# Camera / OCR
CAMERA_INDEX     = 0
FOCUS_VALUE      = 200    # default focus used by capture_image_at_focus()
OCR_WHITELIST    = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-\\/ "

# Scryfall
SCRYFALL_CARD_URL = "https://api.scryfall.com/cards/{set_code}/{collector_number}"