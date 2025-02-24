import logging

logging.basicConfig(
    filename="bot.log",
    format="{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M",
    level=logging.DEBUG,
    encoding="utf-8"
)
logger = logging.getLogger()