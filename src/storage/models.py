from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, Date, DateTime,
    ForeignKey, Index, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(50), default="USA")
    radius: Mapped[int] = mapped_column(Integer, default=100)
    keywords: Mapped[Optional[dict]] = mapped_column(JSON)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    price_min: Mapped[Optional[float]] = mapped_column(Float)
    price_max: Mapped[Optional[float]] = mapped_column(Float)
    condition: Mapped[str] = mapped_column(String(50), default="used")
    listing_age_days: Mapped[int] = mapped_column(Integer, default=7)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs: Mapped[List["ScrapingRun"]] = relationship("ScrapingRun", back_populates="search_config")


class ScrapingRun(Base):
    __tablename__ = "scraping_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, default=date.today)
    source: Mapped[str] = mapped_column(String(50))
    search_config_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("search_configs.id"))
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    new_listings: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="running")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    search_config: Mapped[Optional["SearchConfig"]] = relationship("SearchConfig", back_populates="runs")
    listings: Mapped[List["Listing"]] = relationship("Listing", back_populates="scraping_run")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identity / deduplication
    listing_url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    url_hash: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # Core listing data
    listing_title: Mapped[Optional[str]] = mapped_column(Text)
    equipment_type: Mapped[Optional[str]] = mapped_column(String(100))
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)
    price_raw: Mapped[Optional[str]] = mapped_column(String(50))
    hours: Mapped[Optional[int]] = mapped_column(Integer)

    # Location
    location_city: Mapped[Optional[str]] = mapped_column(String(100))
    location_state: Mapped[Optional[str]] = mapped_column(String(50))
    location_full: Mapped[Optional[str]] = mapped_column(String(200))
    distance_miles: Mapped[Optional[float]] = mapped_column(Float)

    # Seller
    seller_name: Mapped[Optional[str]] = mapped_column(String(200))
    seller_type: Mapped[Optional[str]] = mapped_column(String(50))  # private/dealer/unknown
    seller_phone: Mapped[Optional[str]] = mapped_column(String(50))

    # Content
    description: Mapped[Optional[str]] = mapped_column(Text)
    photos_count: Mapped[int] = mapped_column(Integer, default=0)
    photo_urls: Mapped[Optional[list]] = mapped_column(JSON)

    # Dates
    date_listed: Mapped[Optional[date]] = mapped_column(Date)
    date_found: Mapped[date] = mapped_column(Date, default=date.today)
    last_checked: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Status and scoring
    status: Mapped[str] = mapped_column(String(50), default="new")
    lead_priority: Mapped[Optional[str]] = mapped_column(String(50))
    lead_score: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Search context
    source: Mapped[Optional[str]] = mapped_column(String(50))
    search_keyword: Mapped[Optional[str]] = mapped_column(String(200))
    search_city: Mapped[Optional[str]] = mapped_column(String(100))
    search_radius: Mapped[Optional[int]] = mapped_column(Integer)
    scraping_run_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scraping_runs.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scraping_run: Mapped[Optional["ScrapingRun"]] = relationship("ScrapingRun", back_populates="listings")

    __table_args__ = (
        Index("idx_listing_priority", "lead_priority"),
        Index("idx_listing_status", "status"),
        Index("idx_listing_date_found", "date_found"),
        Index("idx_listing_seller_price", "seller_name", "price"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "listing_title": self.listing_title,
            "equipment_type": self.equipment_type,
            "brand": self.brand,
            "model": self.model,
            "year": self.year,
            "price": self.price,
            "price_raw": self.price_raw,
            "location_full": self.location_full,
            "seller_name": self.seller_name,
            "seller_type": self.seller_type,
            "seller_phone": self.seller_phone,
            "description": self.description,
            "photos_count": self.photos_count,
            "listing_url": self.listing_url,
            "date_listed": str(self.date_listed) if self.date_listed else None,
            "date_found": str(self.date_found) if self.date_found else None,
            "last_checked": str(self.last_checked) if self.last_checked else None,
            "status": self.status,
            "lead_priority": self.lead_priority,
            "lead_score": self.lead_score,
            "source": self.source,
            "search_keyword": self.search_keyword,
            "search_city": self.search_city,
            "notes": self.notes,
        }
