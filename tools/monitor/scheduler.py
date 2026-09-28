import datetime
from typing import Any, Dict, Iterable

from tools.evaluator import FitScorer
from tools.scrapers import ScraperError, get_scraper_for_url


class MonitorScheduler:
    """Scrapes and scores a list of job URLs, splitting them into matches (score >= threshold)
    and rejections. Remembers seen URLs and job IDs so repeat cycles only report new postings."""

    def __init__(self, target_feed_urls: Iterable[str], min_threshold: float = 4.0):
        self.target_feed_urls = list(target_feed_urls)
        self.min_threshold = min_threshold
        self.fit_scorer = FitScorer()
        self.seen = set()

    def run_polling_cycle(self) -> Dict[str, Any]:
        matched, rejected, errors = [], [], []
        for source in self.target_feed_urls:
            if source in self.seen:
                continue
            self.seen.add(source)
            try:
                job = get_scraper_for_url(source).scrape(source)
            except ScraperError as e:
                self.seen.discard(source)  # retry next cycle
                errors.append({"source": source, "error": str(e)})
                continue
            if job["job_id"] in self.seen:
                continue
            self.seen.add(job["job_id"])
            fit = self.fit_scorer.evaluate(job)
            (matched if fit["score"] >= self.min_threshold else rejected).append({"job": job, "fit": fit})

        return {
            "polled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_processed": len(matched) + len(rejected),
            "matched_jobs": matched,
            "rejected_jobs": rejected,
            "errors": errors,
        }
