import datetime
import html
import os
import sqlite3
from typing import Any, Dict, List, Optional

from tools import common

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    job_id TEXT,
    company TEXT,
    role TEXT,
    date_applied TEXT,
    fit_score REAL,
    status TEXT DEFAULT 'APPLIED',
    resume_file_path TEXT,
    cover_letter_file_path TEXT,
    contact_email TEXT,
    follow_up_date TEXT,
    last_updated TEXT
)"""
STATUSES = ("READY_TO_APPLY", "APPLIED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN")


def _md_cell(value: Any) -> str:
    return html.unescape(str(value or "")).replace("|", "\\|").replace("\n", " ").strip()


class ApplicationLogger:
    """Application tracker. SQLite (profile-vault/jobs.db) is the source of truth;
    job_applications.md is regenerated from it after every change, so the two never drift."""

    def __init__(self, tracker_md_path: Optional[str] = None, db_path: Optional[str] = None):
        self.tracker_md_path = tracker_md_path or common.TRACKER_MD
        self.db_path = db_path or common.DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def log(self, job_posting: Dict[str, Any], fit_score: Dict[str, Any], resume_path: str, cover_path: str,
            status: str = "APPLIED", follow_up_days: int = 7) -> Dict[str, Any]:
        """Records one application per job (re-logging the same job updates it)."""
        today = datetime.date.today()
        job_id = job_posting.get("job_id") or f"job_{datetime.datetime.now():%H%M%S}"
        entry = {
            "application_id": f"app_{job_id}",
            "job_id": job_id,
            "company": html.unescape(job_posting.get("company", "Unknown Company")),
            "role": html.unescape(job_posting.get("title", "Unknown Role")),
            "date_applied": today.isoformat(),
            "fit_score": float(fit_score.get("score", 0.0)),
            "status": status.upper(),
            "resume_file_path": resume_path,
            "cover_letter_file_path": cover_path,
            "contact_email": job_posting.get("contact_email", ""),
            "follow_up_date": (today + datetime.timedelta(days=follow_up_days)).isoformat(),
            "last_updated": today.isoformat(),
        }
        with self._connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO applications ({', '.join(entry)}) VALUES ({', '.join('?' * len(entry))})",
                         tuple(entry.values()))
        self.export_markdown()
        return entry

    def update_status(self, app_id_or_job_id: str, new_status: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE applications SET status = ?, last_updated = ? WHERE application_id = ? OR job_id = ?",
                (new_status.upper(), datetime.date.today().isoformat(), app_id_or_job_id, app_id_or_job_id))
            updated = cur.rowcount > 0
        if updated:
            self.export_markdown()
        return updated

    def list_applications(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        query, args = "SELECT * FROM applications", ()
        if status_filter:
            query, args = query + " WHERE UPPER(status) = ?", (status_filter.upper(),)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query + " ORDER BY date_applied DESC, company", args)]

    def export_markdown(self) -> str:
        """Rewrites job_applications.md from the database."""
        apps = self.list_applications()
        counts = {s: sum(1 for a in apps if a["status"] == s) for s in STATUSES}
        lines = [
            "# Job Applications",
            "",
            "Generated from `profile-vault/jobs.db` — edit with `python scripts/track_app.py`, not by hand.",
            "",
            " · ".join(f"{s.replace('_', ' ').title()}: {n}" for s, n in counts.items() if n) or "No applications yet.",
            "",
            "| Date | Company | Role | Fit | Status | Folder | Follow-up | ID |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for a in apps:
            folder = os.path.basename(os.path.dirname(a["resume_file_path"] or "")) or "—"
            lines.append("| " + " | ".join(_md_cell(c) for c in (
                a["date_applied"], a["company"], a["role"], f"{a['fit_score']:.2f}", a["status"],
                folder, a["follow_up_date"], a["job_id"])) + " |")
        with open(self.tracker_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return self.tracker_md_path
