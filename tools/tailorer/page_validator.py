from dataclasses import dataclass, field
from typing import List

from pdfminer.pdfpage import PDFPage

TUNING_GUIDANCE = [
    "Content Pruning: keep the top 2-3 highest-impact bullets per project.",
    "List Spacing: \\setlist[itemize]{noitemsep, topsep=1pt, parsep=0pt}.",
    "Section Headings: \\titlespacing*{\\section}{0pt}{3pt}{2pt}.",
    "Line Spread: \\linespread{0.96} before \\begin{document}.",
    "Margins: tighten \\topmargin / \\textheight (keep 11pt body text).",
]


@dataclass
class PageValidationResult:
    is_valid: bool
    page_count: int
    feedback: str
    tuning_guidance: List[str] = field(default_factory=list)


class PageValidator:
    """Enforces the single-page resume constraint."""

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Page count of a PDF; 0 if the file is missing or not a readable PDF."""
        try:
            with open(pdf_path, "rb") as f:
                return sum(1 for _ in PDFPage.get_pages(f))
        except Exception:  # missing file or any pdfminer parse error
            return 0

    @staticmethod
    def validate_single_page(pdf_path: str) -> bool:
        return PageValidator.get_page_count(pdf_path) == 1

    @staticmethod
    def validate_page_count_with_feedback(pdf_path: str) -> PageValidationResult:
        count = PageValidator.get_page_count(pdf_path)
        if count == 1:
            return PageValidationResult(True, 1, "PDF satisfies the single-page constraint.")
        if count == 0:
            return PageValidationResult(False, 0, f"No readable PDF at {pdf_path}; compile it first.")
        return PageValidationResult(False, count, f"PDF has {count} pages (expected exactly 1).", TUNING_GUIDANCE)
