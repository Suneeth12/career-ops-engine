# Career Ops

An automated command-line job-application and ATS tailoring engine. Give it a job (URL, pasted description, or saved JSON) and it:

1. **ingests** the posting (15 job boards + Oracle HCM + any other URL),
2. **scores fit** 1.0–5.0 against `candidate_profile.json`,
3. **tailors a one-page LaTeX resume** for the role type and compiles it to PDF,
4. writes a **cover letter** and **ATS form answers**,
5. **tracks** the application in SQLite and `job_applications.md`.

---

## Quick start

```powershell
pip install -r requirements.txt
scoop install tectonic                      # LaTeX compiler for resume PDFs
python scripts/apply_all.py "https://jobs.ashbyhq.com/<company>/<job-id>"
```

Result: `profile-vault/applications/<company>-<job_id>/` containing **`resume.pdf`** + **`application.md`**, and a `READY_TO_APPLY` row in the tracker. After you actually submit:

```powershell
python scripts/track_app.py --update <job_id> --status APPLIED
```

Optional: `FIRECRAWL_API_KEY=...` in `.env` for JavaScript-heavy job pages (plain HTTP otherwise).

---

## Commands

All job inputs accept a URL, pasted JD text, or a JobPosting `.json` file.

| Command | Purpose |
|---|---|
| `python scripts/apply_all.py <job> [--threshold 3.5]` | Full pipeline. Stops below the fit threshold. Refuses to log a resume that is not exactly 1 page. |
| `python scripts/scrape_job.py <job> [--out job.json]` | Ingest only; exits 1 if the page can't be fetched. |
| `python scripts/eval_fit.py <job>` | Fit score, matched/missing skills, flags, ATS heuristics. |
| `python scripts/tailor_resume.py <job> --compile` | Tailored resume only (PDF written to `profile-vault/cache/tex/tailored/`). |
| `python scripts/generate_cover.py <job> [--out letter.md]` | Print (and optionally save) the cover letter. |
| `python scripts/form_answers.py <job>` | ATS form answers as JSON. |
| `python scripts/track_app.py --list [--status-filter APPLIED]` | List applications. |
| `python scripts/track_app.py --update <job_id> --status INTERVIEW` | Change status (`READY_TO_APPLY`, `APPLIED`, `INTERVIEW`, `OFFER`, `REJECTED`, `WITHDRAWN`). |
| `python scripts/monitor_daemon.py <url>... [--feeds urls.txt] [--threshold 4.0]` | Score many job URLs, list the good ones. Run daily from a scheduler. |
| `python scripts/verify_application.py <job> [--pdf resume.pdf]` | 7-point package audit. |
| `python scripts/ats_checker.py <resume.pdf>` | Parse a PDF like an ATS and audit it against the profile. |

---

## How it works

### Role detection (AI vs Data Engineering vs Data Analytics)

`tools/common.py::classify_role` reads the **job title** in two passes:

1. **Role noun first:** what the job *is*.
   - `data / analytics / ETL engineer` → **data_engineering**
   - `data / business / BI / MIS / product analyst`, `analytics`, `BI developer` → **data_analytics**
   - `data scientist`, `AI / ML / GenAI / LLM / NLP / CV engineer · developer · scientist · trainee · intern` → **ai**
2. **Domain keywords second:** `RAG`, `LLM`, `ML` → ai; `ETL`, `Spark`, `Airflow`, `dbt` → data_engineering; `SQL`, `BI`, `Tableau` → data_analytics; `software`, `developer`, `SDE` → sde.

All matching is whole-word, so "Mobile" is not "BI", "Storage" is not "RAG", and "International" is not "Intern".

| Title | Role | Template | Summary opens with | Projects preferred |
|---|---|---|---|---|
| Gen AI Developer, ML Engineer, Data Scientist, Senior RAG Engineer | ai | `resume_ai_genai_engineering.tex` | "Gen AI Engineer …" | `category: ai_genai` |
| Data Engineer, AI Data Engineer, Analytics Engineer, ETL Developer | data_engineering | `resume_data_engineering_analytics.tex` | "Data Engineer …" | `data_engineering` |
| Data Analyst, BI Developer, MIS Analyst | data_analytics | `resume_data_engineering_analytics.tex` | "Data Analyst …" | `data_analytics` |
| Software Engineer, SDE, Backend Developer | sde | `ats_resume_template.tex` | "Software Engineer …" | projects using FastAPI/Flask/Docker/AWS/SQL |

"AI Data Engineer" goes to **data_engineering** because the role noun is *Data Engineer*. Data engineering and data analytics share one template; they differ in summary and project choice.

### Fit score
`1 + 4 × (matched skills / required skills)`, then +0.2 for location match (India / remote) or −0.5 if not, and +0.2 if the posted salary meets the minimum (≥ 5 LPA or ≥ $30k). If the JD has no recognisable skills the ratio is 0.5 (neutral → manual review), never a free 5.0. **APPLY** ≥ 4.0 · **MANUAL_REVIEW** ≥ 3.0 · **SKIP** below.

### One-page guarantee
The builder estimates the line budget to choose bullets per project and list spacing. If Tectonic still produces more than one page, `compile_pdf` compacts in steps: spacing → line spread → 2 bullets per project. `apply_all` won't log an overflowing resume.

### No fabrication (design rules)
- An unreachable page raises `IngestionError`; the system never invents a posting.
- Unknown JD skills → empty list, neutral score.
- Resume summary, cover letter and form answers only name skills that `candidate_profile.json` lists (`claimable_skills`).
- Tests use fake pages and a temp directory; they never touch real data.

---

## Repository layout

```
README.md               this file
requirements.txt        jsonschema, pdfminer.six, pytest (+ tectonic binary)
pytest.ini              test discovery limited to tests/
tools/
  common.py             paths, JSON loading, skill matching, role classification
  scrapers/             BOARDS table + router, fetch/parse, Oracle HCM API, cache
  evaluator/            FitScorer, BM25 matcher, ApplicationVerifier
  tailorer/             LaTeXBuilder, CoverLetterGenerator, PageValidator
  form_filler/          AnswerGenerator
  tracker/              ApplicationLogger (SQLite → Markdown)
  monitor/              MonitorScheduler
scripts/                thin CLIs over tools/ (table above)
tests/                  pytest; conftest.py isolates writes and fakes the network
profile-vault/
  candidate_profile.json   single source of truth: contact, education, skills, projects (local/ignored)
  candidate_profile.example.json public template for profile configuration
  templates/               3 LaTeX resume templates (ai, data, default SDE)
  applications/<name>/     resume.pdf + application.md per application — nothing else
  cache/, *.db             git-ignored working data (LaTeX sources, fetched pages)
```

### Adding things
- **A job board:** one row in `BOARDS` in `tools/scrapers/__init__.py`.
- **A project:** add to `candidate_profile.json → projects` with `category` (`ai_genai` / `data_engineering` / `data_analytics` / `sde`), `tech_stack`, 3 `bullets`.
- **A skill the scraper should detect:** `KNOWN_SKILLS` in `tools/scrapers/base.py`.

---

## Tests

```powershell
python -m pytest -m "not live"     # offline (default workflow)
python -m pytest                   # includes 2 live-network tests
```
91 tests. `test_audit_regressions.py` pins each bug fixed in the audit. `test_every_real_application_is_one_pdf_page` checks the real vault: every application folder is exactly `resume.pdf` (1 page) + `application.md`.

---

## Architecture & Design Rules

**Design Invariants:**
- Strict 1-page PDF constraint enforced dynamically via iterative margin and line-spread tuning.
- Decoupled templates with zero personal data leakage in source control.
- Isolated test environment ensuring local candidate databases and trackers remain untouched.


---

## 👤 Author
**Suneeth Reddy Peddamallu** — [GitHub](https://github.com/Suneeth12) • [Portfolio](https://suneeth.live) • [LinkedIn](https://linkedin.com/in/suneeth-reddy-peddamallu)
