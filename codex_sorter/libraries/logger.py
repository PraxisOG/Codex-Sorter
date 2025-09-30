import logging

def get_logger(name: str = "mtg_sorter") -> logging.Logger:
    """Return a module‑level logger that prints to stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:                     # avoid duplicate handlers on reload
        logger.setLevel(logging.DEBUG)           # change to DEBUG while developing
        ch = logging.StreamHandler()
        fmt = "[%(asctime)s] %(levelname)s – %(message)s"
        ch.setFormatter(logging.Formatter(fmt))
        logger.addHandler(ch)
    return logger