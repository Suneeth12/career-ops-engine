"""Oracle Cloud HCM Candidate Experience portals (e.g. Hexaware, *.oraclecloud.com)."""
import json
import re
import urllib.request
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from .base import UA, BaseScraper
from .cache import ScraperCache


class OracleHCMScraper(BaseScraper):
    """Reads requisitions from the recruitingCEJobRequisitionDetails REST endpoint.
    Falls back to generic page/text parsing when no requisition ID is present."""

    HEXAWARE_FUSION_HOST = "https://fa-etqo-saasfaprod1.fa.ocs.oraclecloud.com"
    DEFAULT_SITE_NUMBER = "CX_1"

    def __init__(self):
        super().__init__("ora", "https://jobs.hexaware.com/job")

    def _requisition_info(self, url: str) -> Tuple[Optional[str], str, str]:
        parsed = urlparse(url)
        m = re.search(r"/job/(\d+)", url) or re.search(r"recruitingCEJobRequisitionDetails/(\d+)", url)
        site = re.search(r"/sites/([A-Za-z0-9_]+)", url)
        host = f"{parsed.scheme}://{parsed.netloc}" if "oraclecloud.com" in parsed.netloc.lower() else self.HEXAWARE_FUSION_HOST
        return (m.group(1) if m else None), host, (site.group(1) if site else self.DEFAULT_SITE_NUMBER)

    def _fetch_requisition(self, host: str, req_id: str, site_number: str) -> Optional[Dict[str, Any]]:
        cache_key = f"oracle_api:{host}:{req_id}:{site_number}"
        cached = ScraperCache.get(cache_key)
        if cached:
            return cached
        req = urllib.request.Request(
            f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/{req_id}?expand=all",
            headers={"User-Agent": UA, "Accept": "application/json", "ora-irc-cx-siteNumber": site_number},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError):
            return None
        ScraperCache.set(cache_key, data)
        return data

    def scrape(self, source_input: str) -> Dict[str, Any]:
        cleaned = self.validate_input(source_input)
        if not cleaned.startswith(("http://", "https://")):
            return super().scrape(cleaned)

        req_id, host, site = self._requisition_info(cleaned)
        data = self._fetch_requisition(host, req_id, site) if req_id else None
        if not data or not data.get("Title"):
            return super().scrape(cleaned)

        desc = data.get("ExternalDescriptionStr") or ""
        return self.build_posting(
            desc, cleaned, url_known=True, job_id=req_id,
            company="Hexaware Technologies" if "hexaware" in cleaned.lower() else "Oracle Cloud Employer",
            title=data["Title"],
            location=data.get("PrimaryLocation") or "India",
        )
