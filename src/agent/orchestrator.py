"""
Main orchestrator: ties together scraper → filter → clean → dedup → score → save → export.
Supports both demo (mock) and production (facebook) modes.
"""
import asyncio
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional

from dotenv import load_dotenv

from src.processors.data_cleaner import DataCleaner
from src.processors.deduplicator import Deduplicator
from src.processors.keyword_filter import KeywordFilter
from src.processors.lead_scorer import LeadScorer
from src.scrapers.base_scraper import RawListing
from src.scrapers.facebook_scraper import FacebookScraper
from src.scrapers.mock_scraper import MockScraper
from src.storage.database import (
    complete_run, create_run, get_all_listings, get_run_stats,
    init_db, seed_search_configs, session_scope, upsert_listing,
)
from src.outputs.csv_exporter import CSVExporter
from src.outputs.google_sheets import GoogleSheetsExporter
from src.outputs.report_generator import ReportGenerator
from src.utils.helpers import load_yaml, config_path
from src.utils.logger import get_logger, setup_logger

load_dotenv()
log = get_logger(__name__)


@dataclass
class RunStats:
    total_found: int = 0
    filtered_out: int = 0
    duplicates_skipped: int = 0
    rejected_by_score: int = 0
    new_listings: int = 0
    errors: int = 0
    cities: list = field(default_factory=list)
    keywords: list = field(default_factory=list)


class Orchestrator:
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback or (lambda msg, pct: None)
        self.config = load_yaml(config_path("config.yaml"))
        self.keywords_cfg = load_yaml(config_path("keywords.yaml"))
        self.mode = os.getenv("APP_MODE", self.config["app"].get("mode", "demo"))

        setup_logger(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_file=os.getenv("LOG_FILE", "logs/agent.log"),
        )
        init_db()

    def _get_scraper(self):
        if self.mode == "facebook":
            return FacebookScraper(self.config)
        return MockScraper(self.config)

    def _get_keywords(self) -> List[str]:
        inclusion = self.keywords_cfg.get("inclusion", {})
        return [k for group in inclusion.values() for k in group]

    def _get_active_locations(self) -> List[dict]:
        return [
            loc for loc in self.config["search"]["locations"]
            if loc.get("active", True)
        ]

    async def run(self) -> dict:
        stats = RunStats()
        locations = self._get_active_locations()
        keywords = self._get_keywords()

        self.progress_callback("Initializing database and search configs...", 2)

        with session_scope() as session:
            seed_search_configs(session, locations, keywords)

        stats.cities = [f"{l['city']}, {l['state']}" for l in locations]
        stats.keywords = keywords[:5]  # representative sample for report

        self.progress_callback(f"Starting {self.mode} scraper across {len(locations)} cities...", 5)

        scraper = self._get_scraper()
        all_raw: List[RawListing] = []

        keyword_filter = KeywordFilter(self.keywords_cfg)
        data_cleaner = DataCleaner(self.keywords_cfg)
        lead_scorer = LeadScorer(self.config.get("lead_scoring", {}))

        total_combos = len(keywords) * len(locations)
        done_combos = 0

        with session_scope() as session:
            run_record = create_run(session, source=self.mode)
            run_id = run_record.id
            deduplicator = Deduplicator(session)

            for location in locations:
                city_name = f"{location['city']}, {location['state']}"
                for keyword in keywords:
                    pct = 5 + int((done_combos / total_combos) * 70)
                    self.progress_callback(f"Scraping '{keyword}' in {city_name}...", pct)

                    try:
                        raw_batch = await scraper.scrape(
                            keyword=keyword,
                            city=location["city"],
                            state=location["state"],
                            radius=location.get("radius", 100),
                            price_max=self.config["search"].get("default_price_max"),
                        )
                        stats.total_found += len(raw_batch)

                        # Filter
                        filtered, rejected_log = keyword_filter.filter(raw_batch)
                        stats.filtered_out += len(rejected_log)

                        # Clean
                        cleaned = [data_cleaner.clean(r) for r in filtered]

                        # Dedup
                        unique, dup_log = deduplicator.filter_batch(cleaned)
                        stats.duplicates_skipped += len(dup_log)

                        # Score
                        scored = lead_scorer.score_batch(unique)

                        # Save
                        for listing in scored:
                            listing.scraping_run_id = run_id
                            saved_listing, is_new = upsert_listing(session, listing)
                            if is_new:
                                stats.new_listings += 1

                    except Exception as e:
                        stats.errors += 1
                        log.error(f"Error processing {keyword} in {city_name}: {e}")

                    done_combos += 1

            run_stats_dict = {
                "total_found": stats.total_found,
                "new_listings": stats.new_listings,
                "duplicates_skipped": stats.duplicates_skipped,
                "rejected": stats.filtered_out,
                "errors": stats.errors,
            }
            complete_run(session, run_record, run_stats_dict)

        if hasattr(scraper, "close"):
            await scraper.close()

        self.progress_callback("Generating outputs...", 80)

        with session_scope() as session:
            all_listings = get_all_listings(session, limit=5000)
            today_stats = get_run_stats(session, date.today())

        self._generate_outputs(all_listings, today_stats)

        self.progress_callback("Complete!", 100)

        return {
            "stats": {
                "total_found": stats.total_found,
                "new_listings": stats.new_listings,
                "duplicates_skipped": stats.duplicates_skipped,
                "filtered_out": stats.filtered_out,
                "errors": stats.errors,
            },
            "today_stats": today_stats,
            "cities": stats.cities,
        }

    def _generate_outputs(self, listings, stats: dict) -> None:
        csv_exporter = CSVExporter()
        report_gen = ReportGenerator()

        try:
            csv_exporter.export_all(listings)
            csv_exporter.export_high_priority(listings)
            self.progress_callback("CSV files exported.", 85)
        except Exception as e:
            log.error(f"CSV export failed: {e}")

        try:
            report_gen.generate(listings, stats)
            self.progress_callback("HTML report generated.", 90)
        except Exception as e:
            log.error(f"Report generation failed: {e}")

        if os.getenv("GOOGLE_SPREADSHEET_ID"):
            try:
                sheets = GoogleSheetsExporter()
                sheets.sync_all_leads(listings)
                sheets.sync_high_priority(listings)
                sheets.write_daily_summary(stats)
                self.progress_callback("Google Sheets synced.", 95)
            except Exception as e:
                log.warning(f"Google Sheets sync failed: {e}")
        else:
            log.info("GOOGLE_SPREADSHEET_ID not set — skipping Sheets sync")


def run_sync(progress_callback: Optional[Callable] = None) -> dict:
    """Synchronous wrapper for calling from Streamlit or CLI."""
    orchestrator = Orchestrator(progress_callback=progress_callback)
    return asyncio.run(orchestrator.run())
