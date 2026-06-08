from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)


def with_retry(attempts: int = 3, min_wait: float = 2, max_wait: float = 10):
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


scraper_retry = with_retry(attempts=3, min_wait=3, max_wait=15)
sheets_retry = with_retry(attempts=5, min_wait=2, max_wait=30)
db_retry = with_retry(attempts=3, min_wait=1, max_wait=5)
