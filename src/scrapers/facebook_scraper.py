"""
Facebook Marketplace scraper using Playwright.

Usage flow:
1. First run: browser opens, user logs in manually → session saved to FB_SESSION_FILE
2. Subsequent runs: session loaded, browser runs quietly
3. Rate limits: random delays between every page action
"""
import asyncio
import json
import os
import re
from datetime import date, timedelta
from typing import List, Optional
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout

from src.scrapers.base_scraper import BaseScraper, RawListing
from src.utils.helpers import random_delay, parse_price
from src.utils.logger import get_logger
from src.utils.retry import scraper_retry

log = get_logger(__name__)

FB_MARKETPLACE_BASE = "https://www.facebook.com/marketplace"


class FacebookScraper(BaseScraper):
    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "facebook"
        self.session_file = os.getenv("FB_SESSION_FILE", "credentials/fb_session.json")
        self.headless = config.get("scraper", {}).get("headless", False)
        self.timeout = config.get("scraper", {}).get("timeout_ms", 30000)
        self.min_delay = float(os.getenv("SCRAPER_MIN_DELAY", 2))
        self.max_delay = float(os.getenv("SCRAPER_MAX_DELAY", 5))
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def _launch(self) -> None:
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx_args = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 800},
        }
        if Path(self.session_file).exists():
            with open(self.session_file, "r") as f:
                storage_state = json.load(f)
            ctx_args["storage_state"] = storage_state
            log.info("Loaded existing FB session")

        self._context = await self._browser.new_context(**ctx_args)
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    async def _ensure_logged_in(self, page: Page) -> bool:
        await page.goto("https://www.facebook.com", timeout=self.timeout)
        await random_delay(2, 4)

        if await page.query_selector('[aria-label="Your profile"]'):
            log.info("Already logged in to Facebook")
            return True

        log.warning("Not logged in. Opening browser for manual login...")
        log.warning("Please log in to Facebook in the browser window, then press Enter here.")
        input("Press Enter after you have logged in to Facebook...")

        if self._context:
            state = await self._context.storage_state()
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)
            with open(self.session_file, "w") as f:
                json.dump(state, f)
            log.info(f"Session saved to {self.session_file}")
        return True

    async def _close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    @scraper_retry
    async def scrape(
        self,
        keyword: str,
        city: str,
        state: str,
        radius: int,
        price_max: Optional[float] = None,
    ) -> List[RawListing]:
        if not self._browser:
            await self._launch()

        page = await self._context.new_page()
        listings = []

        try:
            await self._ensure_logged_in(page)

            # Build search URL
            location_slug = f"{city.lower().replace(' ', '-')}-{state.lower()}"
            params = f"query={keyword.replace(' ', '%20')}&radius={radius}"
            if price_max:
                params += f"&maxPrice={int(price_max)}"
            url = f"{FB_MARKETPLACE_BASE}/{location_slug}/search/?{params}"

            log.info(f"Scraping: {keyword} in {city}, {state}")
            await page.goto(url, timeout=self.timeout)
            await random_delay(self.min_delay, self.max_delay)

            # Scroll to load more listings
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await random_delay(1.5, 3)

            # Collect listing cards
            cards = await page.query_selector_all('[data-testid="marketplace_feed_unit"]')
            if not cards:
                # Fallback selector for different FB layouts
                cards = await page.query_selector_all('div[class*="x1lliihq"] a[href*="/marketplace/item/"]')

            log.info(f"Found {len(cards)} cards for '{keyword}' in {city}")
            max_per_search = self.config.get("scraper", {}).get("max_listings_per_search", 50)

            for i, card in enumerate(cards[:max_per_search]):
                try:
                    raw = await self._extract_card(card, keyword, city, state, radius, page)
                    if raw:
                        listings.append(raw)
                    await random_delay(0.3, 0.8)
                except Exception as e:
                    log.warning(f"Error extracting card {i}: {e}")

        except PlaywrightTimeout:
            log.error(f"Timeout scraping {keyword} in {city}")
        except Exception as e:
            log.error(f"Error scraping {keyword} in {city}: {e}")
        finally:
            await page.close()

        return listings

    async def _extract_card(
        self, card, keyword: str, city: str, state: str, radius: int, page: Page
    ) -> Optional[RawListing]:
        try:
            link_el = await card.query_selector("a[href*='/marketplace/item/']")
            if not link_el:
                return None
            href = await link_el.get_attribute("href")
            listing_url = f"https://www.facebook.com{href}" if href and href.startswith("/") else href

            title_el = await card.query_selector("span[class*='x1lliihq']")
            title = (await title_el.inner_text()).strip() if title_el else ""

            price_el = await card.query_selector("span[class*='x193iq5w']")
            price_raw = (await price_el.inner_text()).strip() if price_el else ""

            location_el = await card.query_selector("span[class*='x1jx94hy']")
            location_full = (await location_el.inner_text()).strip() if location_el else f"{city}, {state}"

            # Open listing detail for full data
            detail = await self._scrape_detail(listing_url, page)

            return RawListing(
                listing_url=listing_url or "",
                listing_title=title,
                price_raw=price_raw,
                location_full=location_full,
                seller_name=detail.get("seller_name", ""),
                seller_type=detail.get("seller_type", "unknown"),
                seller_phone=detail.get("phone", ""),
                description=detail.get("description", ""),
                photos_count=detail.get("photos_count", 0),
                photo_urls=detail.get("photo_urls", []),
                date_listed_raw=detail.get("date_listed", ""),
                source="facebook",
                search_keyword=keyword,
                search_city=city,
                search_radius=radius,
                distance_raw=detail.get("distance", ""),
            )
        except Exception as e:
            log.debug(f"Card extraction failed: {e}")
            return None

    async def _scrape_detail(self, url: str, page: Page) -> dict:
        detail = {}
        if not url:
            return detail
        try:
            detail_page = await self._context.new_page()
            await detail_page.goto(url, timeout=self.timeout)
            await random_delay(self.min_delay, self.max_delay)

            desc_el = await detail_page.query_selector('[data-testid="marketplace_pdp_description"]')
            if desc_el:
                detail["description"] = (await desc_el.inner_text()).strip()

            seller_el = await detail_page.query_selector('a[href*="/profile.php"], a[href*="/user/"]')
            if seller_el:
                detail["seller_name"] = (await seller_el.inner_text()).strip()

            phone_match = re.search(
                r"(\+?1?\s?\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4})",
                detail.get("description", ""),
            )
            if phone_match:
                detail["phone"] = phone_match.group(1)

            images = await detail_page.query_selector_all('img[data-visualcompletion="media-vc-image"]')
            detail["photos_count"] = len(images)
            detail["photo_urls"] = [
                await img.get_attribute("src") for img in images[:10] if await img.get_attribute("src")
            ]

            await detail_page.close()
        except Exception as e:
            log.debug(f"Detail page error: {e}")
        return detail

    async def close(self) -> None:
        await self._close()
