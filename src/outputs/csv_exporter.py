import os
from datetime import date
from typing import List
import pandas as pd

from src.storage.models import Listing
from src.utils.logger import get_logger

log = get_logger(__name__)


class CSVExporter:
    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _to_dataframe(self, listings: List[Listing]) -> pd.DataFrame:
        return pd.DataFrame([l.to_dict() for l in listings])

    def export_all(self, listings: List[Listing], run_date: date = None) -> str:
        run_date = run_date or date.today()
        path = os.path.join(self.output_dir, f"leads_{run_date}.csv")
        df = self._to_dataframe(listings)
        df.to_csv(path, index=False)
        log.info(f"Exported {len(listings)} listings to {path}")
        return path

    def export_high_priority(self, listings: List[Listing], run_date: date = None) -> str:
        run_date = run_date or date.today()
        high = [l for l in listings if l.lead_priority == "high"]
        path = os.path.join(self.output_dir, f"high_priority_{run_date}.csv")
        df = self._to_dataframe(high)
        df.to_csv(path, index=False)
        log.info(f"Exported {len(high)} high-priority listings to {path}")
        return path

    def export_by_priority(self, listings: List[Listing], run_date: date = None) -> dict:
        run_date = run_date or date.today()
        paths = {}
        for priority in ("high", "medium", "low"):
            subset = [l for l in listings if l.lead_priority == priority]
            if not subset:
                continue
            path = os.path.join(self.output_dir, f"{priority}_{run_date}.csv")
            self._to_dataframe(subset).to_csv(path, index=False)
            paths[priority] = path
        return paths
