import os
from typing import Any, Dict, Optional, Tuple

from tools.common import PROFILE_PATH, claimable_skills, classify_role, load_json
from .latex_builder import education_facts


class CoverLetterGenerator:
    """3-paragraph cover letter (Markdown + plain text) tailored to a JobPosting.
    Skills named in the letter are always ones the candidate profile actually lists."""

    def __init__(self, master_resume_path: Optional[str] = None):
        self.profile = load_json(master_resume_path or PROFILE_PATH)

    def _project_summary(self, role: str) -> str:
        projs = self.profile.get("projects") or []
        cat_map = {"ai": "ai_genai", "data_engineering": "data_engineering", "data_analytics": "data_analytics"}
        target_cat = cat_map.get(role)
        matched = [p for p in projs if target_cat in (p.get("category") if isinstance(p.get("category"), list) else [p.get("category")])] if target_cat else []
        selected = (matched + [p for p in projs if p not in matched])[:2]
        if not selected:
            return "In my engineering projects, I architected scalable data pipelines and backend microservices with automated validation."
        p1 = selected[0]
        desc1 = (p1.get("bullets") or [p1.get("description", "")])[0].strip()
        summary = f"In my work on {p1.get('name')}, I {desc1[0].lower() + desc1[1:] if desc1 else 'built scalable services.'}"
        if len(selected) > 1:
            p2 = selected[1]
            desc2 = (p2.get("bullets") or [p2.get("description", "")])[0].strip()
            summary += f" I also developed {p2.get('name')}, where I {desc2[0].lower() + desc2[1:] if desc2 else 'implemented robust features.'}"
        return summary

    def _credentials_summary(self) -> str:
        pubs = self.profile.get("publications") or []
        certs = self.profile.get("certifications") or []
        parts = []
        if certs:
            top_certs = ", ".join(certs[:2])
            parts.append(f"hold professional certifications including {top_certs}")
        if pubs:
            pub = pubs[0]
            parts.append(f"authored peer-reviewed research ('{pub.get('title')}') published at {pub.get('venue')}")
        if parts:
            return f"Additionally, I {' and '.join(parts)}. "
        return ""

    def generate_3_paragraphs(self, job_posting: Dict[str, Any]) -> Tuple[str, str, str]:
        job_posting = job_posting or {}
        company = job_posting.get("company") or "your company"
        title = job_posting.get("title") or "open"
        top_skills = ", ".join(claimable_skills(job_posting.get("skills_required"), self.profile))
        edu = education_facts(self.profile)
        student = f"a B.Tech Computer Science student at {edu['school']} University ({edu['cgpa']} CGPA)" if edu.get("school") else "a Computer Science graduate"
        loc = self.profile.get("location") or "Remote"

        p1 = (f"I am writing to apply for the {title} position at {company}. "
              f"As {student}, I am eager to contribute to {company}'s engineering initiatives. "
              f"I am based in {loc} and prepared to deliver immediate technical impact.")

        proj_desc = self._project_summary(classify_role(title))
        p2 = (f"{proj_desc} "
              f"My technical background in {top_skills} aligns directly with {company}'s requirements for the {title} role.")

        cred_desc = self._credentials_summary()
        p3 = (f"{cred_desc}I would welcome the opportunity to discuss how my practical experience and problem-solving drive "
              f"can advance {company}'s engineering goals. Thank you for your time and consideration.")

        return p1, p2, p3

    def letter(self, job_posting: Dict[str, Any]) -> str:
        """The full letter as Markdown (paste-ready: the only markup is the bold signature)."""
        p1, p2, p3 = self.generate_3_paragraphs(job_posting)
        company = (job_posting or {}).get("company") or "Hiring Team"
        p = self.profile
        return (f"Dear Hiring Team at {company},\n\n{p1}\n\n{p2}\n\n{p3}\n\n"
                f"Sincerely,  \n**{p.get('full_name', '')}**  \n{p.get('email', '')} | {p.get('phone', '')} | {p.get('github_url', '')}\n")

    def generate(self, job_posting: Dict[str, Any], out_md: str) -> str:
        """Writes the letter to out_md and returns the path."""
        company = (job_posting or {}).get("company") or "Hiring Team"
        os.makedirs(os.path.dirname(os.path.abspath(out_md)), exist_ok=True)
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(f"# Cover Letter — {company}\n\n{self.letter(job_posting)}")
        return out_md
