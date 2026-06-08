import re
import random
import asyncio
import hashlib
from datetime import datetime, date
from typing import Optional
import yaml
import os


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_url_hash(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()


def parse_price(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(price_str))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def extract_year(text: str) -> Optional[int]:
    matches = re.findall(r"\b(19[89]\d|20[0-2]\d)\b", text)
    return int(matches[0]) if matches else None


def normalize_phone(phone: str) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits if len(digits) >= 10 else None


def today_str() -> str:
    return date.today().isoformat()


def now_str() -> str:
    return datetime.utcnow().isoformat()


async def random_delay(min_s: float = 2, max_s: float = 5) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def truncate(text: str, max_len: int = 500) -> str:
    if not text:
        return ""
    return text[:max_len] + "..." if len(text) > max_len else text


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def config_path(filename: str) -> str:
    return os.path.join(project_root(), "config", filename)
