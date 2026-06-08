from typing import List
from src.scrapers.base_scraper import RawListing
from src.utils.helpers import load_yaml, config_path


class KeywordFilter:
    def __init__(self, keywords_config: dict):
        self.exclusion_terms = [k.lower() for k in keywords_config.get("exclusion", [])]
        self.conditional_exclusion = [k.lower() for k in keywords_config.get("conditional_exclusion", [])]
        inclusion_cfg = keywords_config.get("inclusion", {})
        self.inclusion_terms = [
            k.lower()
            for group in inclusion_cfg.values()
            for k in group
        ]

    @classmethod
    def from_yaml(cls, path: str = None) -> "KeywordFilter":
        cfg = load_yaml(path or config_path("keywords.yaml"))
        return cls(cfg)

    def _text(self, listing: RawListing) -> str:
        return f"{listing.listing_title} {listing.description}".lower()

    def is_excluded(self, listing: RawListing) -> tuple[bool, str]:
        text = self._text(listing)
        for term in self.exclusion_terms:
            if term in text:
                return True, f"excluded keyword: '{term}'"
        for term in self.conditional_exclusion:
            if term in text:
                return True, f"conditional exclusion: '{term}'"
        return False, ""

    def is_relevant(self, listing: RawListing) -> bool:
        text = self._text(listing)
        return any(term in text for term in self.inclusion_terms)

    def filter(self, listings: List[RawListing]) -> tuple[List[RawListing], List[dict]]:
        """Returns (kept, rejected_log)."""
        kept = []
        rejected = []
        for listing in listings:
            excluded, reason = self.is_excluded(listing)
            if excluded:
                rejected.append({"title": listing.listing_title, "reason": reason})
                continue
            if not self.is_relevant(listing):
                rejected.append({"title": listing.listing_title, "reason": "no inclusion keyword matched"})
                continue
            kept.append(listing)
        return kept, rejected
