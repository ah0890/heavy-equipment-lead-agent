#!/usr/bin/env python
"""
CLI entry point for the Heavy Equipment Lead Agent.

Usage:
  python main.py run              # Run with mode from .env (default: demo)
  python main.py run --mode demo  # Force demo mode (mock data)
  python main.py run --mode facebook  # Use real Playwright + FB scraper
  python main.py stats            # Show today's database stats
  python main.py report           # Regenerate today's report from DB
"""
import os
import sys
import click
from dotenv import load_dotenv

load_dotenv()


@click.group()
def cli():
    pass


@cli.command()
@click.option("--mode", default=None, type=click.Choice(["demo", "facebook"]),
              help="Scraper mode: demo (mock data) or facebook (Playwright)")
def run(mode: str):
    """Run the lead scraping agent."""
    if mode:
        os.environ["APP_MODE"] = mode

    effective_mode = os.getenv("APP_MODE", "demo")
    click.echo(f"Starting agent in [{effective_mode.upper()}] mode...")

    def progress(msg: str, pct: int):
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        click.echo(f"\r[{bar}] {pct:3d}% - {msg}", nl=False)
        if pct >= 100:
            click.echo()

    try:
        from src.agent.orchestrator import run_sync
        result = run_sync(progress_callback=progress)

        click.echo("\n" + "=" * 60)
        click.echo("RUN COMPLETE")
        click.echo("=" * 60)
        s = result.get("stats", {})
        click.echo(f"  Total scraped  : {s.get('total_found', 0)}")
        click.echo(f"  New leads      : {s.get('new_listings', 0)}")
        click.echo(f"  Duplicates     : {s.get('duplicates_skipped', 0)}")
        click.echo(f"  Filtered out   : {s.get('filtered_out', 0)}")
        click.echo(f"  Errors         : {s.get('errors', 0)}")
        ts = result.get("today_stats", {})
        click.echo(f"\n  High priority  : {ts.get('high_priority', 0)}")
        click.echo(f"  Medium priority: {ts.get('medium_priority', 0)}")
        click.echo(f"  Low priority   : {ts.get('low_priority', 0)}")
        click.echo("\nReports saved to data/reports/")

    except KeyboardInterrupt:
        click.echo("\nAborted.")
        sys.exit(0)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@cli.command()
def stats():
    """Show today's lead statistics from the database."""
    from src.storage.database import init_db, session_scope, get_run_stats
    init_db()
    with session_scope() as session:
        s = get_run_stats(session)

    click.echo(f"\nToday's Stats ({s['date']})")
    click.echo(f"  Total    : {s['total']}")
    click.echo(f"  High     : {s['high_priority']}")
    click.echo(f"  Medium   : {s['medium_priority']}")
    click.echo(f"  Low      : {s['low_priority']}")
    click.echo(f"  Rejected : {s['rejected']}")

    if s["by_type"]:
        click.echo("\nBy Equipment Type:")
        for eq_type, count in s["by_type"].items():
            click.echo(f"  {eq_type:<20} {count}")

    if s["by_city"]:
        click.echo("\nBy City:")
        for city, count in s["by_city"].items():
            click.echo(f"  {city:<25} {count}")


@cli.command()
def report():
    """Regenerate today's HTML report from existing database records."""
    from src.storage.database import init_db, session_scope, get_all_listings, get_run_stats
    from src.outputs.report_generator import ReportGenerator
    from datetime import date

    init_db()
    with session_scope() as session:
        listings = get_all_listings(session, limit=5000)
        stats = get_run_stats(session, date.today())

    gen = ReportGenerator()
    path = gen.generate(listings, stats)
    click.echo(f"Report saved: {path}")


if __name__ == "__main__":
    cli()
