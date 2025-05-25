import logging
from colorlog import ColoredFormatter

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter(
    fmt="%(log_color)s%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    log_colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'bold_red',
    }
))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
