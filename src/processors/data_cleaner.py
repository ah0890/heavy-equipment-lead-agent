import re
from datetime import date, datetime, timezone
from typing import Optional
from dateutil import parser as dateparser

from src.scrapers.base_scraper import RawListing
from src.storage.models import Listing
from src.utils.helpers import parse_price, extract_year, normalize_phone, make_url_hash, truncate, load_yaml, config_path


class DataCleaner:
    def __init__(self, keywords_config: dict):
        self.known_brands = [b.lower() for b in keywords_config.get("known_brands", [])]
        self.equipment_types = keywords_config.get("equipment_types", {})

    @classmethod
    def from_yaml(cls, path: str = None) -> "DataCleaner":
        cfg = load_yaml(path or config_path("keywords.yaml"))
        return cls(cfg)

    def clean(self, raw: RawListing) -> Listing:
        title = (raw.listing_title or "").strip()
        description = (raw.description or "").strip()
        combined_text = f"{title} {description}".lower()

        listing = Listing(
            listing_url=raw.listing_url or None,
            url_hash=make_url_hash(raw.listing_url) if raw.listing_url else None,
            listing_title=title,
            equipment_type=self._detect_equipment_type(combined_text),
            brand=self._detect_brand(combined_text),
            model=self._detect_model(title),
            year=extract_year(combined_text),
            price=parse_price(raw.price_raw),
            price_raw=raw.price_raw or None,
            location_city=self._parse_city(raw.location_full),
            location_state=self._parse_state(raw.location_full),
            location_full=raw.location_full or None,
            distance_miles=self._parse_distance(raw.distance_raw),
            seller_name=(raw.seller_name or "").strip() or None,
            seller_type=self._normalize_seller_type(raw),
            seller_phone=normalize_phone(raw.seller_phone),
            description=truncate(description, 1000),
            photos_count=raw.photos_count or 0,
            photo_urls=raw.photo_urls or [],
            date_listed=self._parse_date(raw.date_listed_raw),
            date_found=date.today(),
            last_checked=datetime.now(timezone.utc).replace(tzinfo=None),
            status="new",
            source=raw.source or "unknown",
            search_keyword=raw.search_keyword or None,
            search_city=raw.search_city or None,
            search_radius=raw.search_radius or None,
        )
        return listing

    def _detect_equipment_type(self, text: str) -> Optional[str]:
        for eq_type, keywords in self.equipment_types.items():
            if any(kw in text for kw in keywords):
                return eq_type
        return None

    def _detect_brand(self, text: str) -> Optional[str]:
        for brand in self.known_brands:
            if brand in text:
                return brand.upper() if len(brand) <= 4 else brand.title()
        return None

    def _detect_model(self, title: str) -> Optional[str]:
        match = re.search(r"\b([A-Z]{1,3}[\-]?\d{2,4}[A-Z]{0,2}|[A-Z]{2,4}\d{3,4})\b", title)
        return match.group(1) if match else None

    def _parse_city(self, location: str) -> Optional[str]:
        if not location:
            return None
        parts = location.split(",")
        return parts[0].strip() if parts else None

    def _parse_state(self, location: str) -> Optional[str]:
        if not location:
            return None
        parts = location.split(",")
        if len(parts) >= 2:
            state_part = parts[1].strip()
            return state_part.split()[0] if state_part else None
        return None

    def _parse_distance(self, distance_raw: str) -> Optional[float]:
        if not distance_raw:
            return None
        match = re.search(r"(\d+\.?\d*)", distance_raw)
        return float(match.group(1)) if match else None

    def _parse_date(self, date_str: str) -> Optional[date]:
        if not date_str:
            return None
        try:
            return dateparser.parse(date_str).date()
        except Exception:
            return None

    def _normalize_seller_type(self, raw: RawListing) -> str:
        if raw.seller_type in ("private", "dealer"):
            return raw.seller_type
        seller_name = (raw.seller_name or "").lower()
        dealer_indicators = ["equipment", "machinery", "llc", "inc", "corp", "co.", "dealer", "sales", "rentals"]
        if any(ind in seller_name for ind in dealer_indicators):
            return "dealer"
        return "private"
