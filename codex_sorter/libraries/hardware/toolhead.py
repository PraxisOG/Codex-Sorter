import cv2
from ..config import CAMERA_INDEX, FOCUS_VALUE
from codex_sorter.libraries.logger import get_logger

log = get_logger(__name__)

def capture_image_at_focus(
    cam_index: int = CAMERA_INDEX,
    focus: int = FOCUS_VALUE,
    autofocus_off: bool = True,
    warmup_frames: int = 10,
    wait_after_focus_ms: int = 200,
) -> cv2.typing.MatLike | None:
    """Grab a single frame from the webcam with a manual focus value."""
    cap = cv2.VideoCapture(
        cam_index,
        cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0,
    )
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {cam_index}")

    # Turn autofocus off (if the driver supports it)
    if autofocus_off:
        ok = cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        if not ok:
            log.warning("Camera does not expose CAP_PROP_AUTOFOCUS")

    # Set manual focus
    ok_focus = cap.set(cv2.CAP_PROP_FOCUS, float(focus))
    if not ok_focus:
        log.warning("Camera does not expose CAP_PROP_FOCUS – ignoring focus value")

    # Warm‑up frames
    for _ in range(warmup_frames):
        ret, _ = cap.read()
        if not ret:
            log.warning("Failed to read warm‑up frame")
            break

    cv2.waitKey(wait_after_focus_ms)

    # Capture the real image
    ret, frame = cap.read()
    if not ret:
        log.error("Could not capture a frame after warm‑up")
        frame = None

    cap.release()
    cv2.destroyAllWindows()
    return frame