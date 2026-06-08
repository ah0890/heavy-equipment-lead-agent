import os
from datetime import datetime, date
from typing import Optional, List, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from dotenv import load_dotenv

from src.storage.models import Base, Listing, ScrapingRun, SearchConfig
from src.utils.logger import get_logger

load_dotenv()
log = get_logger(__name__)


def get_engine():
    db_url = os.getenv("DATABASE_URL", "sqlite:///data/leads.db")
    if db_url.startswith("postgresql"):
        engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    else:
        # SQLite fallback (useful for demo without PostgreSQL)
        os.makedirs("data", exist_ok=True)
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
    return engine


_engine = None
_SessionLocal = None


def init_db() -> None:
    global _engine, _SessionLocal
    _engine = get_engine()
    Base.metadata.create_all(bind=_engine)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine, expire_on_commit=False)
    log.info("Database initialized")


def get_session() -> sessionmaker:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    SessionLocal = get_session()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Listings CRUD ──────────────────────────────────────────────────────────────

def upsert_listing(session: Session, listing: Listing) -> tuple[Listing, bool]:
    """Insert new listing or update last_checked if URL already exists. Returns (listing, is_new)."""
    existing = session.scalar(
        select(Listing).where(Listing.url_hash == listing.url_hash)
    )
    if existing:
        existing.last_checked = datetime.utcnow()
        existing.status = existing.status  # preserve existing status
        session.flush()
        return existing, False

    session.add(listing)
    session.flush()
    return listing, True


def get_all_listings(
    session: Session,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    limit: int = 1000,
) -> List[Listing]:
    stmt = select(Listing)
    if priority:
        stmt = stmt.where(Listing.lead_priority == priority)
    if status:
        stmt = stmt.where(Listing.status == status)
    if date_from:
        stmt = stmt.where(Listing.date_found >= date_from)
    stmt = stmt.order_by(Listing.lead_score.desc()).limit(limit)
    return list(session.scalars(stmt))


def get_listings_for_dedup(session: Session) -> List[Listing]:
    stmt = select(
        Listing.id, Listing.url_hash, Listing.listing_title,
        Listing.seller_name, Listing.price, Listing.location_city,
    )
    return list(session.execute(stmt))


def update_listing_status(session: Session, listing_id: int, status: str, notes: str = "") -> None:
    session.execute(
        update(Listing).where(Listing.id == listing_id).values(status=status, notes=notes)
    )


# ── Scraping Runs CRUD ─────────────────────────────────────────────────────────

def create_run(session: Session, source: str, config_id: Optional[int] = None) -> ScrapingRun:
    run = ScrapingRun(
        run_date=date.today(),
        source=source,
        search_config_id=config_id,
        status="running",
        started_at=datetime.utcnow(),
    )
    session.add(run)
    session.flush()
    return run


def complete_run(session: Session, run: ScrapingRun, stats: dict) -> None:
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    run.total_found = stats.get("total_found", 0)
    run.new_listings = stats.get("new_listings", 0)
    run.duplicates_skipped = stats.get("duplicates_skipped", 0)
    run.rejected = stats.get("rejected", 0)
    run.errors = stats.get("errors", 0)
    session.flush()


def get_run_stats(session: Session, run_date: Optional[date] = None) -> dict:
    target_date = run_date or date.today()
    listings = session.scalars(
        select(Listing).where(Listing.date_found == target_date)
    ).all()

    stats = {
        "date": str(target_date),
        "total": len(listings),
        "high_priority": sum(1 for l in listings if l.lead_priority == "high"),
        "medium_priority": sum(1 for l in listings if l.lead_priority == "medium"),
        "low_priority": sum(1 for l in listings if l.lead_priority == "low"),
        "rejected": sum(1 for l in listings if l.lead_priority == "rejected"),
        "by_type": {},
        "by_city": {},
    }

    for listing in listings:
        eq_type = listing.equipment_type or "unknown"
        stats["by_type"][eq_type] = stats["by_type"].get(eq_type, 0) + 1
        city = listing.search_city or "unknown"
        stats["by_city"][city] = stats["by_city"].get(city, 0) + 1

    return stats


# ── Search Config CRUD ─────────────────────────────────────────────────────────

def seed_search_configs(session: Session, locations: list, keywords: list) -> None:
    existing = session.scalar(select(SearchConfig).limit(1))
    if existing:
        return  # already seeded

    for loc in locations:
        if not loc.get("active", True):
            continue
        config = SearchConfig(
            name=f"{loc['city']}, {loc['state']}",
            city=loc["city"],
            state=loc["state"],
            country=loc.get("country", "USA"),
            radius=loc.get("radius", 100),
            keywords=keywords,
            active=True,
        )
        session.add(config)
    session.flush()
    log.info(f"Seeded {len(locations)} search configs")
