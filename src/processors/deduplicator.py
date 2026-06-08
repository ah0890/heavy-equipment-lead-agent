from typing import List, Tuple
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.storage.models import Listing
from src.utils.logger import get_logger

log = get_logger(__name__)

TITLE_SIMILARITY_THRESHOLD = 85
COMBINED_THRESHOLD = 70


class Deduplicator:
    def __init__(self, session: Session):
        self.session = session
        self._seen_hashes: set[str] = set()
        self._known: List[dict] = []
        self._load_known()

    def _load_known(self) -> None:
        rows = self.session.execute(
            select(
                Listing.id,
                Listing.url_hash,
                Listing.listing_title,
                Listing.seller_name,
                Listing.price,
                Listing.location_city,
            )
        ).all()
        for row in rows:
            if row.url_hash:
                self._seen_hashes.add(row.url_hash)
            self._known.append({
                "id": row.id,
                "url_hash": row.url_hash,
                "title": (row.listing_title or "").lower(),
                "seller": (row.seller_name or "").lower(),
                "price": row.price,
                "city": (row.location_city or "").lower(),
            })

    def check(self, listing: Listing) -> Tuple[bool, str]:
        """Returns (is_duplicate, reason)."""
        # Fast exact URL match
        if listing.url_hash and listing.url_hash in self._seen_hashes:
            return True, "exact URL match"

        # Fuzzy match against known listings
        title = (listing.listing_title or "").lower()
        seller = (listing.seller_name or "").lower()
        price = listing.price
        city = (listing.location_city or "").lower()

        for known in self._known:
            title_score = fuzz.token_sort_ratio(title, known["title"])
            if title_score < 60:
                continue  # skip clearly different titles early

            price_match = (
                abs((price or 0) - (known["price"] or 0)) < 500
                if price and known["price"]
                else True
            )
            seller_score = fuzz.ratio(seller, known["seller"]) if seller and known["seller"] else 50
            city_match = city == known["city"] if city and known["city"] else True

            if title_score >= TITLE_SIMILARITY_THRESHOLD and price_match and city_match:
                return True, f"fuzzy title match ({title_score}%) with listing #{known['id']}"

            combined = (title_score * 0.5) + (seller_score * 0.3) + (30 if city_match else 0)
            if combined >= COMBINED_THRESHOLD and price_match:
                return True, f"combined similarity score {combined:.0f}"

        return False, ""

    def register(self, listing: Listing) -> None:
        """Add newly saved listing to in-memory index."""
        if listing.url_hash:
            self._seen_hashes.add(listing.url_hash)
        self._known.append({
            "id": listing.id,
            "url_hash": listing.url_hash,
            "title": (listing.listing_title or "").lower(),
            "seller": (listing.seller_name or "").lower(),
            "price": listing.price,
            "city": (listing.location_city or "").lower(),
        })

    def filter_batch(self, listings: List[Listing]) -> Tuple[List[Listing], List[dict]]:
        """Filter a batch: returns (unique_listings, duplicate_log)."""
        unique = []
        duplicate_log = []
        for listing in listings:
            is_dup, reason = self.check(listing)
            if is_dup:
                listing.status = "duplicate"
                duplicate_log.append({"title": listing.listing_title, "reason": reason})
            else:
                unique.append(listing)
                self.register(listing)  # register within-batch dedup
        return unique, duplicate_log
