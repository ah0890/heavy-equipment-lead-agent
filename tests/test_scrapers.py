"""
Tests for the mock scraper.
Run: pytest tests/test_scrapers.py -v
"""
import asyncio
import pytest
from src.scrapers.mock_scraper import MockScraper

CONFIG = {
    "scraper": {"max_listings_per_search": 15, "min_delay": 0, "max_delay": 0},
}


@pytest.fixture
def scraper():
    return MockScraper(CONFIG)


def run(coro):
    return asyncio.run(coro)


class TestMockScraper:
    def test_returns_listings(self, scraper):
        results = run(scraper.scrape("excavator", "Houston", "TX", 100))
        assert len(results) > 0

    def test_all_have_title(self, scraper):
        results = run(scraper.scrape("dozer", "Dallas", "TX", 100))
        assert all(r.listing_title for r in results)

    def test_all_have_url(self, scraper):
        results = run(scraper.scrape("wheel loader", "Phoenix", "AZ", 100))
        assert all(r.listing_url for r in results)

    def test_source_is_mock(self, scraper):
        results = run(scraper.scrape("excavator", "Houston", "TX", 100))
        assert all(r.source == "mock" for r in results)

    def test_search_city_set(self, scraper):
        results = run(scraper.scrape("excavator", "Atlanta", "GA", 150))
        for r in results:
            if r.search_city:  # excluded items may not have it
                assert r.search_city == "Atlanta"

    def test_contains_excluded_items(self, scraper):
        all_results = []
        for _ in range(5):
            all_results.extend(run(scraper.scrape("excavator", "Houston", "TX", 100)))
        excluded_keywords = ["attachment", "toy", "parts only", "wanted", "rental only", "forks only"]
        excluded = [
            r for r in all_results
            if any(kw in r.listing_title.lower() for kw in excluded_keywords)
        ]
        assert len(excluded) > 0, "Mock scraper should inject excluded items for filter testing"

    def test_respects_max_listings(self, scraper):
        results = run(scraper.scrape("excavator", "Chicago", "IL", 100))
        max_allowed = CONFIG["scraper"]["max_listings_per_search"] + 5  # some slack for injected items
        assert len(results) <= max_allowed
