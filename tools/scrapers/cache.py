import hashlib
import json
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from tools.common import CACHE_DIR

TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid"}


def _clean_query(query: str) -> str:
    """Drops tracking params and sorts the rest so equivalent URLs share a key."""
    return urlencode(sorted(
        (k, v) for k, v in parse_qsl(query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ))


def normalize_cache_key(url_or_text: str) -> str:
    """SHA-256 of a normalised URL (fragment kept for SPA portals such as Oracle HCM) or raw text."""
    cleaned = (url_or_text or "").strip()
    if cleaned.startswith(("http://", "https://")):
        p = urlparse(cleaned)
        frag_path, _, frag_query = p.fragment.partition("?")
        frag_query = _clean_query(frag_query)
        fragment = frag_path.rstrip("/") + (f"?{frag_query}" if frag_query else "")
        cleaned = urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.params,
                              _clean_query(p.query), fragment))
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


class ScraperCache:
    """In-memory + on-disk JSON cache for fetched pages and API responses (24h default TTL)."""
    dir = os.path.join(CACHE_DIR, "scrapers")
    _mem: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _file(cls, hash_key: str) -> str:
        return os.path.join(cls.dir, f"{hash_key}.json")

    @classmethod
    def get(cls, key: str, max_age_seconds: int = 86400) -> Optional[Any]:
        if not isinstance(key, str) or not key.strip():
            return None
        hash_key = normalize_cache_key(key)
        record = cls._mem.get(hash_key)
        if record is None:
            try:
                with open(cls._file(hash_key), "r", encoding="utf-8") as f:
                    record = json.load(f)
            except (OSError, ValueError):
                return None
        if time.time() - record.get("timestamp", 0) > max_age_seconds:
            cls._mem.pop(hash_key, None)
            return None
        cls._mem[hash_key] = record
        return record.get("data")

    @classmethod
    def set(cls, key: str, data: Any) -> None:
        if not isinstance(key, str) or not key.strip():
            return
        hash_key = normalize_cache_key(key)
        record = {"key": key, "timestamp": time.time(), "data": data}
        cls._mem[hash_key] = record
        try:
            os.makedirs(cls.dir, exist_ok=True)
            with open(cls._file(hash_key), "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False)
        except OSError:
            pass  # cache is best-effort

    @classmethod
    def clear(cls) -> None:
        cls._mem.clear()
        if os.path.isdir(cls.dir):
            for fname in os.listdir(cls.dir):
                if fname.endswith(".json"):
                    os.remove(os.path.join(cls.dir, fname))
