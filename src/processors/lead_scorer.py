from datetime import date
from typing import Optional
from src.storage.models import Listing
from src.utils.helpers import load_yaml, config_path


RUNNING_KEYWORDS = ["running", "runs great", "ready to work", "operational", "good condition", "excellent"]
EXPORT_KEYWORDS = ["export", "available for export", "export ready", "shipping available"]
CONTACT_KEYWORDS = ["call", "text", "whatsapp", "contact", "message"]


class LeadScorer:
    def __init__(self, scoring_config: dict):
        self.weights = scoring_config.get("weights", {})
        self.high_priority_max_price = scoring_config.get("high_priority_max_price", 50000)

    @classmethod
    def from_yaml(cls, path: str = None) -> "LeadScorer":
        cfg = load_yaml(path or config_path("config.yaml"))
        return cls(cfg.get("lead_scoring", {}))

    def score(self, listing: Listing) -> tuple[float, str]:
        """Returns (score, priority_label)."""
        points = 0.0
        notes = []
        desc = (listing.description or "").lower()
        title = (listing.listing_title or "").lower()
        combined = f"{title} {desc}"

        if listing.price:
            points += self.weights.get("has_price", 10)
            if listing.price <= self.high_priority_max_price:
                points += self.weights.get("price_under_threshold", 20)
                notes.append(f"price under ${self.high_priority_max_price:,}")
        else:
            notes.append("price missing")

        if listing.seller_phone:
            points += self.weights.get("has_phone", 20)
            notes.append("phone listed")
        elif any(kw in combined for kw in CONTACT_KEYWORDS):
            points += self.weights.get("has_seller_contact", 15)
            notes.append("contact info in description")

        if listing.description and len(listing.description) > 80:
            points += self.weights.get("has_description", 10)

        if listing.photos_count and listing.photos_count >= 3:
            points += self.weights.get("has_photos", 10)

        if listing.seller_type == "dealer":
            points += self.weights.get("is_dealer", 5)
            notes.append("dealer")

        if listing.date_listed:
            days_old = (date.today() - listing.date_listed).days
            if days_old <= 3:
                points += self.weights.get("is_recent", 15)
                notes.append("recently listed")
            elif days_old <= 7:
                points += self.weights.get("is_recent", 15) // 2

        has_full_details = all([
            listing.brand, listing.model, listing.year, listing.price, listing.location_full
        ])
        if has_full_details:
            points += self.weights.get("full_details", 10)

        if any(kw in combined for kw in RUNNING_KEYWORDS):
            points += self.weights.get("running_condition_mentioned", 10)
            notes.append("running condition mentioned")

        if any(kw in combined for kw in EXPORT_KEYWORDS):
            points += self.weights.get("export_friendly_mentioned", 5)
            notes.append("export-friendly")

        priority = self._classify(points, listing)
        return round(points, 1), priority

    def _classify(self, score: float, listing: Listing) -> str:
        if listing.status == "rejected":
            return "rejected"
        if score >= 60:
            return "high"
        if score >= 35:
            return "medium"
        if score >= 15:
            return "low"
        return "rejected"

    def score_batch(self, listings: list) -> list:
        for listing in listings:
            score, priority = self.score(listing)
            listing.lead_score = score
            listing.lead_priority = priority
        return listings
