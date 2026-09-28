import hashlib
import math
import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from tools.common import CACHE_DIR, PROFILE_PATH, TEMPLATES_DIR, claimable_skills, classify_role, load_json
from .page_validator import PageValidator

LATEX_SPECIAL_MAP: Dict[str, str] = {
    "\\": r"\textbackslash{}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "%": r"\%", "$": r"\$", "&": r"\&", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
}
LATEX_ESCAPE_REGEX = re.compile(r"([\\~^%&$#_{}])")

# AI-cliché words replaced with plain engineering language.
AI_BUZZWORD_MAP: Dict[str, str] = {
    r"\bspearheaded\b": "led", r"\bdelve\b": "investigate", r"\bdelved\b": "investigated",
    r"\bdelving\b": "investigating", r"\btestament\b": "proof", r"\bpivotal\b": "key",
    r"\bseamless\b": "smooth", r"\bseamlessly\b": "smoothly", r"\bbeacon\b": "guide",
    r"\brealm\b": "field", r"\btapestry\b": "structure", r"\btransformative\b": "major",
    r"\butilize\b": "use", r"\butilized\b": "used", r"\butilizing\b": "using",
    r"\bleverage\b": "use", r"\bleveraged\b": "used", r"\bleveraging\b": "using",
    r"\bin order to\b": "to", r"\bgroundbreaking\b": "new",
}

TEMPLATES = {
    "ai": "resume_ai_genai_engineering.tex",
    "data_engineering": "resume_data_engineering_analytics.tex",
    "data_analytics": "resume_data_engineering_analytics.tex",
}
DEFAULT_TEMPLATE = "ats_resume_template.tex"
PROJECT_CATEGORY = {"ai": "ai_genai", "data_engineering": "data_engineering", "data_analytics": "data_analytics"}
SDE_TECH = ("fastapi", "flask", "docker", "aws", "postgresql", "sqlite", "tectonic", "xgboost")

SUMMARY_RE = re.compile(r"(\\section\{Professional Summary\}\s*\\begin\{itemize\}\[.*?\](?:\s*\\vspace\{.*?\})?\s*\\small\{\\item\{)(.*?)(\}\}\s*\\end\{itemize\})", re.DOTALL)
PROJECTS_RE = re.compile(r"(\\section\{[^}]*Projects\}\s*\\resumeSubHeadingListStart\n)(.*?)(\n\s*\\resumeSubHeadingListEnd)", re.DOTALL | re.IGNORECASE)


def humanize_text(text: str) -> str:
    """Replaces AI-cliché buzzwords with plain wording."""
    for pattern, replacement in AI_BUZZWORD_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def escape_latex(text: Any) -> str:
    """Humanizes, then escapes all 10 LaTeX special characters in a single pass (no double-escaping)."""
    if text is None:
        return ""
    return LATEX_ESCAPE_REGEX.sub(lambda m: LATEX_SPECIAL_MAP[m.group(1)], humanize_text(str(text)))


def education_facts(profile: Dict[str, Any]) -> Dict[str, str]:
    """Short school name and CGPA from the profile, e.g. {'school': 'NIT', 'cgpa': '8.75 / 10.0'}."""
    edu = (profile.get("education") or [{}])[0]
    inst = str(edu.get("institution", ""))
    short = re.search(r"\(([^)]+)\)\s*$", inst)
    return {"school": short.group(1) if short else inst, "cgpa": str(edu.get("cgpa", ""))}


class LaTeXBuilder:
    """Tailors a single-page LaTeX resume (summary + projects) and compiles it with Tectonic."""

    def __init__(self, profile_path: Optional[str] = None) -> None:
        self.profile_path = profile_path or PROFILE_PATH

    def _load_profile(self) -> Dict[str, Any]:
        return load_json(self.profile_path)

    def get_template_for_job(self, job_title: str) -> str:
        return os.path.join(TEMPLATES_DIR, TEMPLATES.get(classify_role(job_title), DEFAULT_TEMPLATE))

    def build_customization_params(self, job_posting: Dict[str, Any], fit_score: Dict[str, Any]) -> Dict[str, Any]:
        profile = self._load_profile()
        title = job_posting.get("title") or "Software Engineer"
        # Only skills backed by the profile are ever highlighted.
        skills = claimable_skills(fit_score.get("tech_stack_overlap") or job_posting.get("skills_required"), profile, limit=6)
        top = ", ".join(skills[:4])
        edu = education_facts(profile)
        student = f"B.Tech CSE student at {edu['school']} (CGPA: {edu['cgpa']})"
        role = classify_role(title)
        summary = {
            "ai": f"Gen AI Engineer and {student} specializing in {top}, foundational ML, NLP, and scalable AI model deployment. "
                  "Experienced in vector retrieval architectures, Transformer fine-tuning, and containerized FastAPI microservices.",
            "data_engineering": f"Data Engineer specializing in {top}, distributed data processing, and cloud pipeline architecture.",
            "data_analytics": f"Data Analyst and {student} specializing in {top}, exploratory data analysis, and automated MIS reporting. "
                              "Experienced in analyzing operational metrics, SQL CTEs/joins, and data integrity audits.",
            "sde": f"Computer Science undergraduate and Software Engineer specializing in {top}, "
                   "Data Structures & Algorithms, and scalable distributed microservices.",
            "sdet": f"SDET and {student} specializing in test automation, quality engineering, {top}, "
                    "and automated verification pipelines with strict CI/CD quality benchmarks.",
            "product_management": f"Product Manager and {student} with a strong engineering foundation in {top}, "
                                  "0-to-1 feature delivery, UI/UX optimization, and data-driven product analytics.",
            "founders_office": f"Founder's Office generalist and {student} specializing in 0-to-1 systems execution, "
                               f"rapid prototyping with {top}, AI workflows, and cross-functional operations.",
        }.get(role, f"Software Engineer & Analyst specializing in {top}, Data Structures & Algorithms, and system optimization.")
        return {
            "job_id": job_posting.get("job_id", "job"),
            "target_role_title": title,
            "highlight_skills": skills,
            "tailored_summary": summary,
        }

    def _select_projects(self, projects: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        if role == "sde":
            sde = [p for p in projects if any(t in " ".join(p.get("tech_stack", [])).lower() for t in SDE_TECH)]
            return sde[:3] if len(sde) >= 3 else projects[:3]
        if role == "sdet":
            sdet = [p for p in projects if any(k in (p.get("name", "") + " " + p.get("description", "")).lower()
                                              for k in ("pipeline", "evaluation", "validation", "verification", "harness", "fastapi"))]
            return sdet[:3] if len(sdet) >= 3 else projects[:3]
        if role == "product_management":
            pm = [p for p in projects if any(k in (p.get("name", "") + " " + p.get("description", "")).lower()
                                             for k in ("dashboard", "career ops", "sales", "rag", "analytics"))]
            return pm[:3] if len(pm) >= 3 else projects[:3]
        if role == "founders_office":
            fo = [p for p in projects if any(k in (p.get("name", "") + " " + p.get("description", "")).lower()
                                             for k in ("autonomous", "career ops", "rag", "pipeline"))]
            return fo[:3] if len(fo) >= 3 else projects[:3]
        cat = PROJECT_CATEGORY.get(role)
        if not cat:
            return projects[:3]
        in_cat = [p for p in projects if cat in (p.get("category") if isinstance(p.get("category"), list) else [p.get("category")])]
        return (in_cat + [p for p in projects if p not in in_cat])[:3]

    def generate_latex_resume(self, params: Dict[str, Any], output_path: str) -> str:
        profile = self._load_profile()
        title = params.get("target_role_title", "")
        template = self.get_template_for_job(title)
        with open(template, "r", encoding="utf-8") as f:
            tex = f.read()

        summary = escape_latex(params.get("tailored_summary") or profile.get("summary", ""))

        # Space budget: estimate fixed lines to pick bullets per project and list spacing for one page.
        summary_lines = max(1, math.ceil(len(summary) / 95.0))
        overhead = 6 + summary_lines + 4 + 5 + 4 + 4 * len(profile.get("experience") or [])
        proj_lines = max(12, 52 - overhead)
        bullets_per_proj = 2 if proj_lines < 18 else 3
        itemsep = "0.8pt" if proj_lines < 15 else "1.0pt" if proj_lines < 20 else "1.2pt"

        blocks = []
        for proj in self._select_projects(profile.get("projects", []), classify_role(title)):
            bullets = [escape_latex(b) for b in proj.get("bullets", [proj.get("description", "")])[:bullets_per_proj] if b]
            items = "\n".join(f"    \\resumeItem{{{b}}}" for b in bullets)
            blocks.append(
                f"      \\resumeProjectHeading\n"
                f"          {{\\textbf{{{escape_latex(proj.get('name', ''))}}} $|$ \\emph{{{escape_latex(', '.join(proj.get('tech_stack', [])[:5]))}}}}}{{}}\n"
                f"          \\resumeItemListStart\n{items}\n          \\resumeItemListEnd"
            )

        if not SUMMARY_RE.search(tex):
            raise ValueError(f"Template has no 'Professional Summary' block to tailor: {template}")
        tex = SUMMARY_RE.sub(lambda m: f"{m.group(1)}\n     {summary}\n    {m.group(3)}", tex)
        if blocks:
            tex = PROJECTS_RE.sub(lambda m: m.group(1) + "\n" + "\n".join(blocks) + m.group(3), tex)
        tex = re.sub(r"(\\newcommand\{\\resumeItemListStart\}\{[^\n]*?itemsep=)\d+(?:\.\d+)?pt", rf"\g<1>{itemsep}", tex)

        # Dynamically inject candidate heading
        full_name = escape_latex(profile.get("full_name") or "Firstname Lastname")
        email = profile.get("email") or "firstname.lastname@example.com"
        phone = profile.get("phone") or "+1 (555) 000-0000"
        loc = escape_latex(profile.get("location") or "City, State / Remote")
        portfolio = profile.get("portfolio_url") or "https://yourportfolio.dev"
        portfolio_clean = re.sub(r"^https?://", "", portfolio).rstrip("/")
        github = profile.get("github_url") or "https://github.com/yourusername"
        github_clean = re.sub(r"^https?://", "", github).rstrip("/")
        linkedin = profile.get("linkedin_url") or "https://linkedin.com/in/yourusername"
        linkedin_clean = re.sub(r"^https?://", "", linkedin).rstrip("/")

        heading_block = (
            f"\\begin{{center}}\n"
            f"    \\textbf{{\\Huge \\scshape {full_name}}} \\\\ \\vspace{{2pt}}\n"
            f"    \\small {loc} $|$ {phone} $|$ {email} $|$ \\href{{{portfolio}}}{{\\underline{{{portfolio_clean}}}}} \\\\ \\vspace{{1pt}}\n"
            f"    \\small \\href{{{github}}}{{\\underline{{{github_clean}}}}} $|$ \\href{{{linkedin}}}{{\\underline{{{linkedin_clean}}}}}\n"
            f"\\end{{center}}"
        )
        tex = re.sub(r"%----------HEADING----------\s*\\begin\{center\}.*?\\end\{center\}",
                     lambda _: f"%----------HEADING----------\n{heading_block}", tex, flags=re.DOTALL)

        # Dynamically inject education
        edu_list = profile.get("education", [])
        if edu_list:
            edu = edu_list[0]
            inst = escape_latex(edu.get("institution", "National Institute of Technology"))
            deg = escape_latex(edu.get("degree", "B.Tech in Computer Science and Engineering"))
            grad = escape_latex(str(edu.get("graduation_year", "2026")))
            cgpa = escape_latex(str(edu.get("cgpa", "")))
            cgpa_str = f"CGPA: {cgpa}" if cgpa else ""
            date_range = f"Aug 2022 -- May {grad}" if grad else "Aug 2022 -- May 2026"
            tex = re.sub(
                r"(\\section\{Education\}\s*\\resumeSubHeadingListStart\s*\\resumeSubheading\s*\{)[^}]*(\}\{)[^}]*(\}\s*\{)[^}]*(\}\{)[^}]*(\})",
                lambda m: f"{m.group(1)}{inst}{m.group(2)}{date_range}{m.group(3)}{deg}{m.group(4)}{cgpa_str}{m.group(5)}",
                tex
            )

        # Dynamically inject competitive profiles
        leetcode_url = profile.get("leetcode_url", "")
        codechef_url = profile.get("codechef_url", "")
        lc_user = leetcode_url.rstrip("/").split("/")[-1] if leetcode_url else ""
        cc_user = codechef_url.rstrip("/").split("/")[-1] if codechef_url else ""
        if lc_user or cc_user:
            prof_str = f"\\item \\textbf{{Profiles:}} LeetCode ({escape_latex(lc_user)}) $|$ CodeChef ({escape_latex(cc_user)})"
            tex = re.sub(r"\\item \\textbf\{(?:Competitive )?Profiles:\}.*", lambda _: prof_str, tex)

        # Dynamically inject publications & certifications
        certs = profile.get("certifications", [])
        pubs = profile.get("publications", [])
        if certs or pubs:
            cert_items = []
            for pub in pubs[:1]:
                title_p = escape_latex(pub.get("title", ""))
                venue_p = escape_latex(pub.get("venue", ""))
                cert_items.append(f"      \\item \\textbf{{Peer-Reviewed Paper:}} \"{title_p}\" -- \\emph{{{venue_p}}}")
            for cert in certs[:3]:
                cert_clean = escape_latex(cert)
                cert_items.append(f"      \\item {cert_clean}")
            cert_block = "\n".join(cert_items)
            tex = re.sub(
                r"(\\section\{Publications \\& Certifications\}\s*\\begin\{itemize\}\[[^\]]*?\](?:\s*\\vspace\{.*?\})?\s*\\small\{\n)(.*?)(\n\s*\}\s*\\end\{itemize\})",
                lambda m: f"{m.group(1)}{cert_block}{m.group(3)}",
                tex,
                flags=re.DOTALL
            )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tex)
        return output_path

    def compile_pdf(self, tex_path: str, output_dir: Optional[str] = None, force_recompile: bool = False) -> str:
        """Compiles with Tectonic (cached by source SHA-256), auto-compacting if it spills past one page.
        Raises RuntimeError if Tectonic is missing or compilation fails."""
        tectonic = shutil.which("tectonic")
        if not tectonic:
            raise RuntimeError("Tectonic not found on PATH (install: scoop install tectonic).")

        output_dir = output_dir or os.path.dirname(os.path.abspath(tex_path))
        os.makedirs(output_dir, exist_ok=True)
        target = os.path.join(output_dir, os.path.splitext(os.path.basename(tex_path))[0] + ".pdf")

        with open(tex_path, "r", encoding="utf-8") as f:
            tex = f.read()
        cache_dir = os.path.join(CACHE_DIR, "tectonic")
        os.makedirs(cache_dir, exist_ok=True)
        cached = os.path.join(cache_dir, hashlib.sha256(tex.encode("utf-8")).hexdigest() + ".pdf")
        if not force_recompile and os.path.exists(cached) and os.path.getsize(cached) > 0:
            if PageValidator.get_page_count(cached) <= 1:
                shutil.copyfile(cached, target)
                return target

        def run() -> None:
            if os.path.exists(target):
                os.remove(target)  # never mistake a stale PDF for a fresh one
            res = subprocess.run([tectonic, "-o", output_dir, tex_path], capture_output=True, text=True, timeout=120)
            if res.returncode != 0 or not os.path.exists(target):
                raise RuntimeError(f"Tectonic failed for {tex_path}:\n{res.stderr[-2000:]}")

        run()
        compactions = [
            # Pass 1: standard margins & itemsep tightening
            lambda t: re.sub(r"\\addtolength\{\\textheight\}\{[0-9.]+in\}", r"\\addtolength{\\textheight}{1.42in}",
                             re.sub(r"\\addtolength\{\\topmargin\}\{-[0-9.]+in\}", r"\\addtolength{\\topmargin}{-0.72in}",
                                    re.sub(r"itemsep=\d+(?:\.\d+)?pt", "itemsep=0.5pt",
                                           re.sub(r"\\vspace\{3pt\}\\scshape", r"\\vspace{2pt}\\scshape", t)))),
            # Pass 2: linespread 0.96
            lambda t: re.sub(r"\\linespread\{[0-9.]+\}", r"\\linespread{0.96}", t) if "\\linespread" in t
                      else t.replace("\\begin{document}", "\\linespread{0.96}\n\\begin{document}", 1),
            # Pass 3: clamp project bullets to 2
            self._clamp_project_bullets,
            # Pass 4: deeper linespread 0.93 & margins to -0.75in / 1.45in
            lambda t: re.sub(r"\\linespread\{[0-9.]+\}", r"\\linespread{0.93}",
                             re.sub(r"\\addtolength\{\\textheight\}\{[0-9.]+in\}", r"\\addtolength{\\textheight}{1.45in}",
                                    re.sub(r"\\addtolength\{\\topmargin\}\{-[0-9.]+in\}", r"\\addtolength{\\topmargin}{-0.75in}",
                                           re.sub(r"itemsep=\d+(?:\.\d+)?pt", "itemsep=0.3pt", t)))),
            # Pass 5: ultra-compact linespread 0.90 & itemsep 0.0pt
            lambda t: re.sub(r"\\linespread\{[0-9.]+\}", r"\\linespread{0.90}",
                             re.sub(r"itemsep=\d+(?:\.\d+)?pt", "itemsep=0.0pt",
                                    re.sub(r"\\vspace\{-5pt\}\}", r"\\vspace{-7pt}}", t))),
        ]
        for compact in compactions:
            if PageValidator.get_page_count(target) <= 1:
                break
            tex = compact(tex)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex)
            run()

        if PageValidator.get_page_count(target) <= 1:
            shutil.copyfile(target, cached)
            with open(tex_path, "r", encoding="utf-8") as f:
                final_tex = f.read()
            final_cached = os.path.join(cache_dir, hashlib.sha256(final_tex.encode("utf-8")).hexdigest() + ".pdf")
            if final_cached != cached:
                shutil.copyfile(target, final_cached)
        return target

    @staticmethod
    def _clamp_project_bullets(tex: str, keep: int = 2) -> str:
        out, in_proj, count = [], False, 0
        for line in tex.split("\n"):
            if r"\resumeProjectHeading" in line:
                in_proj, count = True, 0
            elif in_proj and r"\resumeItemListEnd" in line:
                in_proj = False
            elif in_proj and r"\resumeItem{" in line:
                count += 1
                if count > keep:
                    continue
            out.append(line)
        return "\n".join(out)
