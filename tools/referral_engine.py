"""Referral Intake & Profile Optimization Engine.

Processes referral alerts from Telegram/WhatsApp/Slack (text, screenshots, or dropzone files):
- Extracts company, role, batch eligibility, stipend/salary, location, notice period, and JD links.
- Identifies application channel: EMAIL, GOOGLE_FORM, CAREER_LINK, or OTHER.
- Evaluates candidate fit against candidate_profile.json.
- Tailors single-page LaTeX resume and compiles it to PDF using Tectonic.
- Generates channel-specific submission deliverables:
    - EMAIL: email_draft.md (recipient, subject line, tailored pitch, links, mailto link)
    - GOOGLE_FORM: form_responses.md (comprehensive field answers, links, tailored short answers)
    - CAREER_LINK: portal_submission.md (direct link, tailored cover letter, ATS answers)
    - SUBMISSION_CHECKLIST.md (60-second action plan)
- Logs to SQLite (jobs.db) and Markdown tracker (job_applications.md).
"""
import datetime
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from tools import common
from tools.evaluator import FitScorer
from tools.form_filler import AnswerGenerator
from tools.scrapers.base import BaseScraper, IngestionError, KNOWN_SKILLS
from tools.tailorer import CoverLetterGenerator, LaTeXBuilder, PageValidator
from tools.tracker import ApplicationLogger


def parse_referral_text(text: str) -> Dict[str, Any]:
    """Parses raw text from a Telegram referral post into structured referral data."""
    if not text or not text.strip():
        raise IngestionError("Referral text cannot be empty.")

    cleaned = text.strip()

    # 1. Key fields extraction
    field_patterns = {
        "company": r"(?:company|org|organization)\s*[:\-–—]\s*([^\n\r]+)",
        "role": r"(?:role|title|position|job role)\s*[:\-–—]\s*([^\n\r]+)",
        "batch": r"(?:batch|eligible batch(?:es)?|year of graduation|yoe)\s*[:\-–—]\s*([^\n\r]+)",
        "salary_raw": r"(?:salary|stipend|ctc|compensation|pkg|package)\s*[:\-–—]\s*([^\n\r]+)",
        "location": r"(?:location|loc|city|work location)\s*[:\-–—]\s*([^\n\r]+)",
        "notice_period": r"(?:notice period|notice)\s*[:\-–—]\s*([^\n\r]+)",
    }

    parsed: Dict[str, Any] = {}
    for key, pat in field_patterns.items():
        m = re.search(pat, cleaned, re.IGNORECASE)
        parsed[key] = m.group(1).strip() if m else None

    # Fallback for company/title from BaseScraper if missing
    scraper = BaseScraper()
    co, ti, loc = scraper.extract_company_title_location(cleaned)
    company = parsed["company"] or (co if co != "Unknown Company" else "Referral Company")
    title = parsed["role"] or (ti if ti != "Software / Data Role" else "Software / Data Role")
    location = parsed["location"] or loc

    # 2. Batch eligibility (target is 2026 batch)
    batch_str = parsed["batch"] or ""
    batch_eligible = True
    if batch_str:
        batch_eligible = "2026" in batch_str or "any" in batch_str.lower() or "fresher" in batch_str.lower()

    # 3. Salary / Stipend parsing
    salary_raw = parsed["salary_raw"] or ""
    salary_range = scraper.parse_salary_range(f"{salary_raw} {cleaned}")

    # 4. Employment & Workplace type
    employment_type = scraper.parse_employment_type(cleaned)
    workplace_type = scraper.parse_workplace_type(cleaned, location)

    # 5. JD URL (Google Drive, Docs, Notion, web links)
    jd_url_match = re.search(r"(?:jd|job details|description)\s*[:\-–—]?\s*(https?://[^\s\n\r]+)", cleaned, re.IGNORECASE)
    jd_url = jd_url_match.group(1).strip() if jd_url_match else None
    if not jd_url:
        drive_match = re.search(r"(https?://(?:drive\.google\.com|docs\.google\.com/document)[^\s\n\r]+)", cleaned, re.IGNORECASE)
        if drive_match:
            jd_url = drive_match.group(1).strip()

    # 6. Application Channel Detection
    # Look for "How to Apply" section
    how_to_apply_match = re.search(r"how to apply\s*[:\-–—]?\s*(.+)", cleaned, re.IGNORECASE | re.DOTALL)
    apply_section = how_to_apply_match.group(1) if how_to_apply_match else cleaned

    # Check for Email
    email_match = re.search(r"(?:share your (?:resume|cv)|send your (?:resume|cv|application)|email|mail(?:to)?|at)\s*[:\-–—]?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", apply_section, re.IGNORECASE)
    if not email_match:
        # Generic email search in apply section
        generic_email = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", apply_section)
        if generic_email:
            email_match = generic_email

    # Check for Google Form
    gform_match = re.search(r"(https?://(?:docs\.google\.com/forms|forms\.gle)[^\s\n\r]+)", apply_section)
    if not gform_match:
        gform_match = re.search(r"(https?://(?:docs\.google\.com/forms|forms\.gle)[^\s\n\r]+)", cleaned)

    # Check for Career Portal Link
    portal_match = None
    all_urls = re.findall(r"https?://[^\s\n\r\<\>\"']+", apply_section)
    for u in all_urls:
        if not ("docs.google.com" in u or "forms.gle" in u or "drive.google.com" in u):
            portal_match = u
            break

    # Determine channel
    channel = "OTHER"
    target = ""
    email_subject = None
    collateral = []

    if email_match:
        channel = "EMAIL"
        target = email_match.group(1).strip()
        # Check if email subject hint was specified
        subj_m = re.search(r"subject\s*[:\-–—]\s*([^\n\r]+)", apply_section, re.IGNORECASE)
        if subj_m:
            email_subject = subj_m.group(1).strip()
        # Check requested collateral
        if "cv" in apply_section.lower() or "resume" in apply_section.lower():
            collateral.append("Resume (PDF)")
        if "github" in apply_section.lower():
            collateral.append("GitHub Profile Link")
        if "linkedin" in apply_section.lower():
            collateral.append("LinkedIn Profile Link")
        if "portfolio" in apply_section.lower():
            collateral.append("Portfolio Link")
    elif gform_match:
        channel = "GOOGLE_FORM"
        target = gform_match.group(1).strip()
    elif portal_match:
        channel = "CAREER_LINK"
        target = portal_match.strip()

    # 7. Skills required
    skills_found = [s for s in KNOWN_SKILLS if common.contains_term(s, f"{title} {cleaned}")]

    # 8. Experience years
    exp_years = scraper.parse_experience_years(cleaned)

    # Generate job_id
    clean_company = re.sub(r"[^a-z0-9]+", "", company.lower())[:8] or "comp"
    clean_title = re.sub(r"[^a-z0-9]+", "", title.lower())[:8] or "role"
    raw_hash = common.slugify(f"{clean_company}-{clean_title}")[:12]
    job_id = f"ref_{clean_company}_{raw_hash}"

    return {
        "job_id": job_id,
        "company": company,
        "title": title,
        "batch": batch_str or "Any",
        "batch_eligible": batch_eligible,
        "location": location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
        "salary_range": salary_range,
        "salary_raw": salary_raw,
        "notice_period": parsed["notice_period"] or "Immediate to Serving Notice Period",
        "jd_url": jd_url,
        "application_channel": channel,
        "apply_target": target,
        "email_subject_hint": email_subject,
        "collateral_requested": collateral or ["Resume (PDF)"],
        "skills_required": skills_found,
        "experience_required_years": exp_years,
        "raw_description": cleaned,
        "source_url": target or jd_url or "https://t.me/referral_post",
        "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


class ReferralProcessor:
    """End-to-end processor for referral posts:
    Ingestion -> Fit Scoring -> Tailored 1-page Resume -> Channel-Specific Deliverables -> Tracker.
    """

    def __init__(self, profile_path: Optional[str] = None):
        self.profile = common.load_json(profile_path or common.PROFILE_PATH)
        self.meta = common.load_json(common.META_PATH)
        self.scorer = FitScorer()
        self.builder = LaTeXBuilder()
        self.cover_gen = CoverLetterGenerator()
        self.answer_gen = AnswerGenerator()
        self.logger = ApplicationLogger()

    def process(self, referral_input: str, min_score_threshold: float = 1.0) -> Dict[str, Any]:
        # 1. Parse input
        print("\n[1/6] Ingesting referral post...")
        job = parse_referral_text(referral_input)
        print(f"    Company: {job['company']} | Role: {job['title']}")
        print(f"    Channel: {job['application_channel']} -> {job['apply_target']}")
        print(f"    Batch: {job['batch']} (2026 Eligible: {'YES' if job['batch_eligible'] else 'NO'})")

        # 2. Fit scoring
        print("[2/6] Scoring candidate fit...")
        fit = self.scorer.evaluate(job)
        score = fit["score"]
        print(f"    Fit Score: {score:.2f} / 5.0 -> {fit['recommendation']}")
        print(f"    Matched Skills: {', '.join(fit['tech_stack_overlap']) or 'None detected'}")

        if score < min_score_threshold:
            print(f"    ABORTED: score {score:.2f} < threshold {min_score_threshold}.")
            return {"status": "ABORTED", "reason": f"Score {score:.2f} < threshold {min_score_threshold}", "job": job, "fit": fit}

        # Setup destination directory
        folder_slug = f"{common.slugify(job['company'])}-{job['job_id']}"
        out_dir = os.path.join(common.APPLICATIONS_DIR, folder_slug)
        os.makedirs(out_dir, exist_ok=True)

        # 3. Tailor and compile resume
        print("[3/6] Tailoring and compiling 1-page resume...")
        params = self.builder.build_customization_params(job, fit)
        cache_tex = os.path.join(common.CACHE_DIR, "tex", job["job_id"], "resume.tex")
        tex_path = self.builder.generate_latex_resume(params, cache_tex)
        pdf_path = self.builder.compile_pdf(tex_path, output_dir=out_dir)
        pages = PageValidator.get_page_count(pdf_path)
        print(f"    Resume compiled: {pdf_path} ({pages} page)")

        # 4. Generate Channel-Specific Deliverables
        # 4. Generate Channel-Specific Collateral Text
        print("[4/6] Generating channel submission collateral...")
        channel = job["application_channel"]
        checklist_text = self._build_submission_checklist_text(job, fit, pdf_path, out_dir)
        channel_text = ""
        if channel == "EMAIL":
            channel_text = self._build_email_draft_text(job, fit)
        elif channel == "GOOGLE_FORM":
            channel_text = self._build_form_responses_text(job, fit)
        elif channel == "CAREER_LINK":
            channel_text = self._build_portal_submission_text(job, fit)
        else:
            channel_text = self._build_email_draft_text(job, fit) + "\n\n---\n\n" + self._build_form_responses_text(job, fit)

        # 5. Generate Master application.md (strictly 2 files: resume.pdf + application.md)
        print("[5/6] Building unified application package...")
        letter = self.cover_gen.letter(job)
        answers = self.answer_gen.generate(job)
        app_md = os.path.join(out_dir, "application.md")
        with open(app_md, "w", encoding="utf-8") as f:
            f.write(self._render_master_app_md(job, fit, letter, answers, checklist_text, channel_text))

        deliverables = {"application_md": app_md, "resume_pdf": pdf_path}

        # 6. Log to Tracker
        print("[6/6] Logging to jobs tracker...")
        tracker_entry = self.logger.log(job, fit, pdf_path, app_md, status="READY_TO_APPLY")
        print(f"    Logged as {tracker_entry['application_id']} -> READY_TO_APPLY")

        return {
            "status": "SUCCESS",
            "job": job,
            "fit": fit,
            "pdf_path": pdf_path,
            "pages": pages,
            "out_dir": out_dir,
            "deliverables": deliverables,
            "tracker_entry": tracker_entry,
        }

    def _build_email_draft_text(self, job: Dict[str, Any], fit: Dict[str, Any]) -> str:
        """Generates email draft text customized to recipient, subject line, and role pitch."""
        to_email = job["apply_target"]
        company = job["company"]
        role = job["title"]
        role_type = common.classify_role(role)

        if job.get("email_subject_hint"):
            subject = f"{job['email_subject_hint']} - {self.profile.get('full_name')} (Immediate Joiner)"
        else:
            subject = f"Application: {role} - {self.profile.get('full_name')} (Immediate Joiner)"

        skills_str = ", ".join(common.claimable_skills(job.get("skills_required"), self.profile))
        project_pitch = self.cover_gen._project_summary(role_type)

        edu = (self.profile.get("education") or [{}])[0]
        school = edu.get("institution", "National Institute of Technology")
        degree = edu.get("degree", "B.Tech in Computer Science and Engineering")
        cgpa = edu.get("cgpa", "")
        grad_year = edu.get("graduation_year", "")
        cgpa_str = f" with an {cgpa} CGPA" if cgpa else ""
        batch_str = f" ({grad_year} Batch)" if grad_year else ""

        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {role} position. "
            f"I am a final-year {degree} student at {school}"
            f"{cgpa_str}{batch_str} and an immediate joiner (0-day notice period).\n\n"
            f"{project_pitch}\n\n"
            f"My technical background in {skills_str} aligns directly with {company}'s requirements. "
            f"I have attached my tailored resume (PDF) for your review. You can also explore my live work and code below:\n\n"
            f"• Portfolio: {self.profile.get('portfolio_url')}\n"
            f"• GitHub: {self.profile.get('github_url')}\n"
            f"• LinkedIn: {self.profile.get('linkedin_url')}\n\n"
            f"I would welcome the opportunity to connect and discuss how my skills and execution drive can add immediate value to {company}.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Best regards,\n\n"
            f"{self.profile.get('full_name')}\n"
            f"{self.profile.get('email')} | {self.profile.get('phone')}\n"
        )

        return (
            f"## Email Application Draft\n\n"
            f"> [!IMPORTANT]\n"
            f"> **Recipient:** `{to_email}`  \n"
            f"> **Subject:** `{subject}`  \n"
            f"> **Attachment:** Attach `resume.pdf` located in this folder.\n\n"
            f"### Email Body (Copy & Paste)\n\n"
            f"```text\n{body}```\n\n"
            f"### Verification Checklist\n"
            f"- [ ] Recipient set to `{to_email}`\n"
            f"- [ ] Subject line set to `{subject}`\n"
            f"- [ ] `resume.pdf` attached\n"
            f"- [ ] Sent\n"
        )

    def _build_form_responses_text(self, job: Dict[str, Any], fit: Dict[str, Any]) -> str:
        """Generates copy-paste responses for Google Form fields."""
        answers = self.answer_gen.generate(job)
        company = job["company"]
        role = job["title"]
        target = job["apply_target"]
        sal = job.get("salary_raw") or "Aligned with posted role"

        edu = (self.profile.get("education") or [{}])[0]
        school = edu.get("institution", "National Institute of Technology")
        degree = edu.get("degree", "B.Tech in Computer Science and Engineering")
        cgpa = edu.get("cgpa", "")
        grad_year = edu.get("graduation_year", "")
        loc = self.profile.get("location", "Bengaluru, India")

        return (
            f"## Google Form Application Responses\n\n"
            f"- **Form URL:** [{target}]({target})\n"
            f"- **Role:** {role}\n"
            f"- **Batch:** {job.get('batch')} (Candidate: {grad_year} Batch — Eligible)\n"
            f"- **Stipend/CTC:** {sal}\n\n"
            f"### Standard Form Fields (Copy & Paste Ready)\n\n"
            f"| Form Question / Field | Ready Answer |\n"
            f"|---|---|\n"
            f"| **Full Name** | `{self.profile.get('full_name')}` |\n"
            f"| **Email Address** | `{self.profile.get('email')}` |\n"
            f"| **Phone Number** | `{self.profile.get('phone')}` |\n"
            f"| **College / University** | `{school}` |\n"
            f"| **Degree / Branch** | `{degree}` |\n"
            f"| **CGPA / Percentage** | `{cgpa}` |\n"
            f"| **Graduation Year / Batch** | `{grad_year}` |\n"
            f"| **Current Location** | `{loc}` |\n"
            f"| **Preferred Location / Relocation** | `Willing to relocate to {job.get('location')} / Open to remote & on-site` |\n"
            f"| **Notice Period / Availability** | `Immediate Joiner (0 days notice period)` |\n"
            f"| **Current CTC / Stipend** | `₹0 (Fresher / Student)` |\n"
            f"| **Expected CTC / Stipend** | `{answers['salary_expectations']}` |\n"
            f"| **LinkedIn Profile** | `{self.profile.get('linkedin_url')}` |\n"
            f"| **GitHub Profile** | `{self.profile.get('github_url')}` |\n"
            f"| **Portfolio / Website** | `{self.profile.get('portfolio_url')}` |\n"
            f"| **LeetCode Profile** | `{self.profile.get('leetcode_url')}` |\n"
            f"| **Resume File** | Upload `resume.pdf` from this directory |\n\n"
            f"### Short-Answer Narrative Questions\n\n"
            f"#### Q: Why do you want to join {company} as {role}?\n"
            f"```text\n{answers['why_join_company']}\n```\n\n"
            f"#### Q: Tell us about a key project you built or measurable delivery in the past 12 months?\n"
            f"```text\n{answers['measurable_outcome_past_12m']}\n```\n\n"
            f"#### Q: What is your technical background relevant to this role?\n"
            f"```text\n{answers['search_motivation']}\n```\n"
        )

    def _build_portal_submission_text(self, job: Dict[str, Any], fit: Dict[str, Any]) -> str:
        """Generates application packet text for external career portal links."""
        company = job["company"]
        role = job["title"]
        target = job["apply_target"]
        answers = self.answer_gen.generate(job)
        edu = (self.profile.get("education") or [{}])[0]
        school = edu.get("institution", "National Institute of Technology")
        degree = edu.get("degree", "B.Tech in Computer Science and Engineering")
        cgpa = edu.get("cgpa", "")
        grad_year = edu.get("graduation_year", "")
        college_summary = f"{school} ({degree} {grad_year}, {cgpa} CGPA)" if cgpa else f"{school} ({degree} {grad_year})"

        return (
            f"## Career Portal Application Details\n\n"
            f"- **Application Link:** [{target}]({target})\n"
            f"- **Role:** {role}\n"
            f"- **Fit Score:** {fit['score']:.2f} / 5.0 ({fit['recommendation']})\n\n"
            f"### ATS Form Quick Answers\n\n"
            f"- **Full Name:** {self.profile.get('full_name')}\n"
            f"- **Email:** {self.profile.get('email')}\n"
            f"- **Phone:** {self.profile.get('phone')}\n"
            f"- **College:** {college_summary}\n"
            f"- **Notice Period:** Immediate (0 days)\n"
            f"- **Salary Expectation:** {answers['salary_expectations']}\n"
            f"- **LinkedIn:** {self.profile.get('linkedin_url')}\n"
            f"- **GitHub:** {self.profile.get('github_url')}\n"
            f"- **Portfolio:** {self.profile.get('portfolio_url')}\n"
            f"- **Resume:** Upload `resume.pdf`\n"
        )

    def _build_submission_checklist_text(self, job: Dict[str, Any], fit: Dict[str, Any],
                                        pdf_path: str, out_dir: str) -> str:
        """Generates a 60-second actionable checklist."""
        channel = job["application_channel"]
        company = job["company"]
        role = job["title"]

        if channel == "EMAIL":
            steps = [
                f"1. Open your email client and compose a message to `{job['apply_target']}`.",
                f"2. Verify recipient is `{job['apply_target']}` and subject is set.",
                f"3. Attach `resume.pdf` from this directory.",
                f"4. Click Send!",
                f"5. Run `python scripts/track_app.py --update {job['job_id']} --status APPLIED`.",
            ]
        elif channel == "GOOGLE_FORM":
            steps = [
                f"1. Open the form: [{job['apply_target']}]({job['apply_target']}).",
                f"2. Copy-paste standard answers and short-answers from below field by field.",
                f"3. Upload `resume.pdf` when prompted for CV/Resume.",
                f"4. Submit the form.",
                f"5. Run `python scripts/track_app.py --update {job['job_id']} --status APPLIED`.",
            ]
        elif channel == "CAREER_LINK":
            steps = [
                f"1. Open the application portal: [{job['apply_target']}]({job['apply_target']}).",
                f"2. Fill applicant details and paste the cover letter below.",
                f"3. Upload `resume.pdf`.",
                f"4. Submit the application.",
                f"5. Run `python scripts/track_app.py --update {job['job_id']} --status APPLIED`.",
            ]
        else:
            steps = [
                f"1. Review `resume.pdf` in this directory.",
                f"2. Submit via the preferred channel.",
                f"3. Update status in tracker: `python scripts/track_app.py --update {job['job_id']} --status APPLIED`.",
            ]

        return (
            f"## ⚡ 60-Second Submission Checklist\n\n"
            f"> [!TIP]\n"
            f"> **Application Channel:** `{channel}`  \n"
            f"> **Target:** `{job['apply_target']}`  \n"
            f"> **Resume Ready:** `resume.pdf` (1 Page Verified)\n\n"
            f"### Action Items:\n"
            + "\n".join(steps) + "\n"
        )

    def _render_master_app_md(self, job: Dict[str, Any], fit: Dict[str, Any],
                              letter: str, answers: Dict[str, Any],
                              checklist_text: str, channel_text: str) -> str:
        lines = [
            f"# {job['title']} — {job['company']}",
            "",
            f"- **Channel:** `{job['application_channel']}` -> `{job['apply_target']}`",
            f"- **Batch:** {job['batch']} (2026 Eligible: {'YES' if job['batch_eligible'] else 'NO'})",
            f"- **Location:** {job['location']} ({job['workplace_type']}, {job['employment_type']})",
            f"- **Compensation:** {job.get('salary_raw') or 'N/A'}",
            f"- **Fit Score:** {fit['score']:.2f} / 5.0 — {fit['recommendation']}",
            f"- **Matched Skills:** {', '.join(fit['tech_stack_overlap']) or '—'}",
            f"- **Missing Skills:** {', '.join(fit['missing_skills']) or '—'}",
            f"- **Resume:** `resume.pdf` (1 page guaranteed)",
            "",
            checklist_text,
            "",
            channel_text,
            "",
            "## Cover Letter",
            "",
            letter,
            "",
            "## Form Answers (Complete)",
            "",
        ]
        for k, v in answers.items():
            if k == "job_id" or v in ("", None):
                continue
            val_str = str(v) if not isinstance(v, dict) else " ".join(str(v.get(x, "")) for x in ("amount", "currency", "unit"))
            lines.append(f"**{k.replace('_', ' ').title()}:** {val_str}  ")
        return "\n".join(lines) + "\n"
