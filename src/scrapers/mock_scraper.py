"""
Mock scraper that generates realistic heavy equipment listings for demo purposes.
Simulates duplicates, excluded items, and varying completeness levels.
"""
import random
import asyncio
from datetime import date, timedelta
from typing import List, Optional
from faker import Faker

from src.scrapers.base_scraper import BaseScraper, RawListing

fake = Faker()

BRANDS = ["CAT", "Komatsu", "Hitachi", "John Deere", "Kobelco", "Volvo", "Doosan", "Hyundai", "Case", "JCB"]
MODELS = {
    "excavator": ["320", "330", "PC200", "PC300", "ZX200", "ZX330", "210LC", "350LC", "SK210", "EC220"],
    "dozer": ["D6", "D8", "D65", "D155", "850", "750", "700", "500"],
    "wheel loader": ["950", "980", "WA380", "WA470", "L150", "L180", "721", "821"],
    "motor grader": ["140M", "120M", "GD655", "GD675", "772", "870"],
    "compactor": ["CS533", "CS563", "BW213", "CA602", "SD116"],
}
EQUIPMENT_TYPES = list(MODELS.keys())
EXCLUDED_ITEMS = [
    "Excavator bucket attachment", "Forks only - forklift attachment",
    "Mini excavator toy model", "Wanted: looking for bulldozer",
    "Hydraulic attachment - parts only", "Tires only - heavy equipment",
    "Manual for CAT 320", "Rental only - excavator",
]
CONDITIONS = ["Good running condition", "Excellent shape", "Runs great, ready to work",
              "Some wear, runs fine", "Good condition for age", "Well maintained"]
SELLER_TYPES = ["private", "private", "private", "dealer", "dealer", "unknown"]
PHONE_PATTERNS = ["({a}) {b}-{c}", "{a}-{b}-{c}", "+1 {a} {b} {c}"]


def _random_phone() -> str:
    if random.random() < 0.6:
        a, b, c = fake.numerify("###"), fake.numerify("###"), fake.numerify("####")
        pattern = random.choice(PHONE_PATTERNS)
        return pattern.format(a=a, b=b, c=c)
    return ""


def _random_price(equipment_type: str) -> str:
    ranges = {
        "excavator": (15000, 95000),
        "dozer": (20000, 110000),
        "wheel loader": (18000, 85000),
        "motor grader": (25000, 120000),
        "compactor": (12000, 60000),
    }
    lo, hi = ranges.get(equipment_type, (10000, 80000))
    price = random.randint(lo // 1000, hi // 1000) * 1000
    return f"${price:,}"


def _random_listing(keyword: str, city: str, state: str, radius: int, source_index: int) -> RawListing:
    eq_type = random.choice(EQUIPMENT_TYPES)
    brand = random.choice(BRANDS)
    model = random.choice(MODELS.get(eq_type, ["Unknown"]))
    year = random.randint(2000, 2020)
    hours = random.randint(1000, 12000)
    price_str = _random_price(eq_type)
    seller_type = random.choice(SELLER_TYPES)

    title_patterns = [
        f"{year} {brand} {model} {eq_type.title()}",
        f"{brand} {model} {eq_type.title()} - {year}",
        f"{year} {brand} {eq_type.title()} {model} - {hours} hours",
        f"Used {brand} {model} {eq_type.title()} {year}",
    ]
    title = random.choice(title_patterns)

    city_state = f"{city}, {state}"
    distance = round(random.uniform(5, radius * 0.9), 1)

    condition = random.choice(CONDITIONS)
    desc_parts = [condition, f"{hours} hours on machine."]
    if random.random() > 0.5:
        desc_parts.append("Ready to work. Serious buyers only.")
    if random.random() > 0.6:
        desc_parts.append("Available for export.")
    description = " ".join(desc_parts)

    phone = _random_phone()
    photos = random.randint(0, 12)

    days_ago = random.randint(0, 14)
    listed_date = (date.today() - timedelta(days=days_ago)).isoformat()

    url_id = f"{source_index:06d}"
    listing_url = f"https://www.facebook.com/marketplace/item/{url_id}"

    return RawListing(
        listing_url=listing_url,
        listing_title=title,
        price_raw=price_str,
        location_full=city_state,
        seller_name=fake.name() if seller_type == "private" else f"{fake.company()} Equipment",
        seller_type=seller_type,
        seller_phone=phone,
        description=description,
        photos_count=photos,
        photo_urls=[f"https://cdn.example.com/photo_{url_id}_{i}.jpg" for i in range(photos)],
        date_listed_raw=listed_date,
        source="mock",
        search_keyword=keyword,
        search_city=city,
        search_radius=radius,
        distance_raw=f"{distance} miles away",
    )


def _excluded_listing(city: str, state: str, keyword: str) -> RawListing:
    title = random.choice(EXCLUDED_ITEMS)
    return RawListing(
        listing_url=f"https://www.facebook.com/marketplace/item/{fake.numerify('######')}",
        listing_title=title,
        price_raw=f"${random.randint(100, 5000)}",
        location_full=f"{city}, {state}",
        seller_name=fake.name(),
        seller_type="private",
        description="See title.",
        source="mock",
        search_keyword=keyword,
        search_city=city,
    )


class MockScraper(BaseScraper):
    """Generates realistic fake listings to demonstrate the full pipeline."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "mock"
        self._counter = 1000

    async def scrape(
        self,
        keyword: str,
        city: str,
        state: str,
        radius: int,
        price_max: Optional[float] = None,
    ) -> List[RawListing]:
        await asyncio.sleep(0.05)  # simulate network delay

        max_per_search = self.config.get("scraper", {}).get("max_listings_per_search", 20)
        count = random.randint(max(3, max_per_search // 3), max_per_search)

        listings = []

        # Normal listings
        for _ in range(count):
            self._counter += 1
            listings.append(_random_listing(keyword, city, state, radius, self._counter))

        # Inject 1-2 excluded items to prove filtering works
        for _ in range(random.randint(1, 2)):
            listings.append(_excluded_listing(city, state, keyword))

        # Inject 1 duplicate (same URL as an earlier listing)
        if listings and random.random() > 0.5:
            dup = listings[0]
            listings.append(RawListing(
                listing_url=dup.listing_url,  # same URL → duplicate
                listing_title=dup.listing_title,
                price_raw=dup.price_raw,
                location_full=dup.location_full,
                seller_name=dup.seller_name,
                source="mock",
                search_keyword=keyword,
                search_city=city,
            ))

        random.shuffle(listings)
        return listings
