from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date


@dataclass
class RawListing:
    """Unprocessed listing data as collected from any source."""
    listing_url: str = ""
    listing_title: str = ""
    price_raw: str = ""
    location_full: str = ""
    seller_name: str = ""
    seller_type: str = "unknown"
    seller_phone: str = ""
    description: str = ""
    photos_count: int = 0
    photo_urls: List[str] = field(default_factory=list)
    date_listed_raw: str = ""
    source: str = ""
    search_keyword: str = ""
    search_city: str = ""
    search_radius: int = 100
    distance_raw: str = ""
    extra: dict = field(default_factory=dict)


class BaseScraper(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.source_name = "unknown"

    @abstractmethod
    async def scrape(
        self,
        keyword: str,
        city: str,
        state: str,
        radius: int,
        price_max: Optional[float] = None,
    ) -> List[RawListing]:
        """Scrape listings for a single keyword + location combination."""
        ...

    async def scrape_all(
        self,
        keywords: List[str],
        locations: List[dict],
        price_max: Optional[float] = None,
        progress_callback=None,
    ) -> List[RawListing]:
        results = []
        total = len(keywords) * len(locations)
        done = 0
        for location in locations:
            for keyword in keywords:
                try:
                    batch = await self.scrape(
                        keyword=keyword,
                        city=location["city"],
                        state=location["state"],
                        radius=location.get("radius", 100),
                        price_max=price_max,
                    )
                    results.extend(batch)
                except Exception as e:
                    pass  # caller handles errors via orchestrator
                done += 1
                if progress_callback:
                    progress_callback(done, total, keyword, location["city"])
        return results
