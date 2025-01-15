# config/logging_config.py

import logging
import os
from logging.handlers import RotatingFileHandler
from .settings import LOG_DIR, LOG_FILE

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('pair_trading_logger')
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
file_handler.setLevel(logging.DEBUG)

console_format = logging.Formatter('%(levelname)s - %(message)s')
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

console_handler.setFormatter(console_format)
file_handler.setFormatter(file_format)

if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
