import sys
import os
from loguru import logger


def setup_logger(log_level: str = "INFO", log_file: str = "logs/agent.log") -> None:
    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger.add(
        log_file,
        level=log_level,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
    )


def get_logger(name: str):
    return logger.bind(name=name)
