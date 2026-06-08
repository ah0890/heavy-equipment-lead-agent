"""
Tests for keyword filter, data cleaner, lead scorer, and deduplicator.
Run: pytest tests/ -v
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from src.scrapers.base_scraper import RawListing
from src.processors.keyword_filter import KeywordFilter
from src.processors.data_cleaner import DataCleaner
from src.processors.lead_scorer import LeadScorer
from src.storage.models import Listing


# ── Fixtures ───────────────────────────────────────────────────────────────────

KEYWORDS_CFG = {
    "inclusion": {
        "main": ["excavator", "dozer", "wheel loader"],
        "brand_based": ["CAT excavator", "komatsu dozer"],
    },
    "exclusion": ["toy", "attachment", "parts only", "wanted", "rental only"],
    "conditional_exclusion": ["mini", "compact"],
    "known_brands": ["CAT", "Komatsu", "Hitachi", "John Deere", "Volvo"],
    "equipment_types": {
        "excavator": ["excavator", "trackhoe"],
        "dozer": ["dozer", "bulldozer"],
        "loader": ["wheel loader", "front loader"],
    },
}

SCORING_CFG = {
    "high_priority_max_price": 50000,
    "weights": {
        "has_price": 10, "price_under_threshold": 20, "has_seller_contact": 15,
        "has_phone": 20, "has_description": 10, "has_photos": 10,
        "is_dealer": 5, "is_recent": 15, "full_details": 10,
        "running_condition_mentioned": 10,
    },
}


def make_raw(title="2015 CAT 320 Excavator", description="Good running condition", price="$35,000"):
    return RawListing(
        listing_url="https://facebook.com/marketplace/item/123456",
        listing_title=title,
        price_raw=price,
        location_full="Houston, TX",
        seller_name="John Smith",
        seller_type="private",
        seller_phone="(713) 555-1234",
        description=description,
        photos_count=5,
        source="mock",
        search_keyword="excavator",
        search_city="Houston",
    )


def make_listing(**kwargs) -> Listing:
    defaults = dict(
        listing_url="https://facebook.com/marketplace/item/999",
        url_hash="abc123",
        listing_title="2018 CAT 320 Excavator",
        equipment_type="excavator",
        brand="CAT",
        model="320",
        year=2018,
        price=42000,
        price_raw="$42,000",
        location_full="Houston, TX",
        location_city="Houston",
        seller_name="John Smith",
        seller_type="private",
        seller_phone="(713) 555-0000",
        description="Good running condition. Ready to work.",
        photos_count=6,
        date_listed=date.today(),
        date_found=date.today(),
        status="new",
        source="mock",
    )
    defaults.update(kwargs)
    return Listing(**defaults)


# ── KeywordFilter tests ────────────────────────────────────────────────────────

class TestKeywordFilter:
    def setup_method(self):
        self.kf = KeywordFilter(KEYWORDS_CFG)

    def test_relevant_listing_passes(self):
        raw = make_raw(title="2015 CAT 320 Excavator")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 1
        assert len(rejected) == 0

    def test_excluded_keyword_rejected(self):
        raw = make_raw(title="Excavator bucket attachment only")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 0
        assert len(rejected) == 1
        assert "attachment" in rejected[0]["reason"]

    def test_toy_rejected(self):
        raw = make_raw(title="CAT toy excavator model")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 0

    def test_mini_conditional_exclusion(self):
        raw = make_raw(title="Mini excavator 2020")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 0
        assert "conditional" in rejected[0]["reason"]

    def test_wanted_rejected(self):
        raw = make_raw(title="Wanted: Looking for used dozer")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 0

    def test_no_inclusion_keyword_rejected(self):
        # "Ford F150" has no inclusion keyword and no exclusion keyword match
        raw = make_raw(title="Ford F150 pickup 2020 for sale")
        kept, rejected = self.kf.filter([raw])
        assert len(kept) == 0
        assert "inclusion" in rejected[0]["reason"]

    def test_batch_mixed(self):
        raws = [
            make_raw(title="2018 Komatsu D65 Dozer"),
            make_raw(title="Toy excavator model"),
            make_raw(title="CAT wheel loader 2016"),
            make_raw(title="Parts only - dozer parts"),
        ]
        kept, rejected = self.kf.filter(raws)
        assert len(kept) == 2
        assert len(rejected) == 2


# ── DataCleaner tests ──────────────────────────────────────────────────────────

class TestDataCleaner:
    def setup_method(self):
        self.cleaner = DataCleaner(KEYWORDS_CFG)

    def test_price_parsed(self):
        raw = make_raw(price="$42,500")
        listing = self.cleaner.clean(raw)
        assert listing.price == 42500.0

    def test_price_missing_is_none(self):
        raw = make_raw(price="")
        listing = self.cleaner.clean(raw)
        assert listing.price is None

    def test_year_extracted_from_title(self):
        raw = make_raw(title="2016 CAT 320 Excavator")
        listing = self.cleaner.clean(raw)
        assert listing.year == 2016

    def test_brand_detected(self):
        raw = make_raw(title="Komatsu PC200 Excavator")
        listing = self.cleaner.clean(raw)
        assert listing.brand is not None
        assert "komatsu" in listing.brand.lower()

    def test_equipment_type_detected(self):
        raw = make_raw(title="John Deere 850 Dozer")
        listing = self.cleaner.clean(raw)
        assert listing.equipment_type == "dozer"

    def test_city_parsed(self):
        raw = make_raw()
        raw.location_full = "Dallas, TX"
        listing = self.cleaner.clean(raw)
        assert listing.location_city == "Dallas"
        assert listing.location_state == "TX"

    def test_dealer_seller_type_inferred(self):
        raw = make_raw()
        raw.seller_name = "Gulf Coast Equipment LLC"
        raw.seller_type = "unknown"
        listing = self.cleaner.clean(raw)
        assert listing.seller_type == "dealer"

    def test_url_hash_generated(self):
        raw = make_raw()
        listing = self.cleaner.clean(raw)
        assert listing.url_hash is not None
        assert len(listing.url_hash) == 32


# ── LeadScorer tests ───────────────────────────────────────────────────────────

class TestLeadScorer:
    def setup_method(self):
        self.scorer = LeadScorer(SCORING_CFG)

    def test_high_priority_full_details(self):
        listing = make_listing(price=35000, seller_phone="(713) 555-0000", photos_count=6,
                               description="Good running condition. Ready to work.")
        score, priority = self.scorer.score(listing)
        assert priority == "high"
        assert score >= 60

    def test_no_price_lowers_score(self):
        listing = make_listing(price=None, seller_phone=None, photos_count=0, description="")
        score, priority = self.scorer.score(listing)
        assert priority in ("low", "rejected")

    def test_expensive_machine_medium_priority(self):
        listing = make_listing(price=120000, seller_phone=None, photos_count=2,
                               description="Good excavator")
        score, priority = self.scorer.score(listing)
        assert priority in ("medium", "low")

    def test_phone_adds_points(self):
        listing_with = make_listing(seller_phone="(713) 555-0000")
        listing_without = make_listing(seller_phone=None)
        score_with, _ = self.scorer.score(listing_with)
        score_without, _ = self.scorer.score(listing_without)
        assert score_with > score_without

    def test_score_batch_assigns_all(self):
        listings = [make_listing() for _ in range(5)]
        scored = self.scorer.score_batch(listings)
        assert all(l.lead_score is not None for l in scored)
        assert all(l.lead_priority is not None for l in scored)

    def test_running_condition_boosts_score(self):
        with_kw = make_listing(description="Runs great, ready to work immediately.")
        without_kw = make_listing(description="Excavator for sale.")
        score_with, _ = self.scorer.score(with_kw)
        score_without, _ = self.scorer.score(without_kw)
        assert score_with > score_without


# ── Integration: filter → clean → score ───────────────────────────────────────

class TestPipeline:
    def test_full_pipeline(self):
        kf = KeywordFilter(KEYWORDS_CFG)
        cleaner = DataCleaner(KEYWORDS_CFG)
        scorer = LeadScorer(SCORING_CFG)

        raws = [
            make_raw("2019 CAT 320 Excavator - excellent condition", price="$38,000"),
            make_raw("Toy excavator for kids"),
            make_raw("2015 Komatsu D65 Dozer - runs great", price="$45,000"),
            make_raw("Excavator bucket attachment only"),
        ]

        kept, rejected = kf.filter(raws)
        assert len(kept) == 2
        assert len(rejected) == 2

        cleaned = [cleaner.clean(r) for r in kept]
        scored = scorer.score_batch(cleaned)

        assert all(l.lead_score is not None for l in scored)
        assert any(l.lead_priority == "high" for l in scored)
