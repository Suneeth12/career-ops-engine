# Agent Protocol: Career Ops & Profile Optimization

This repository powers an automated job application, ATS scoring, and resume tailoring engine.

---

## 1. Environment & Runtime Invariants
- **Host OS**: Windows 11 with PowerShell 7 (`pwsh`).
- **CLI Commands**: Always prefix external commands (`python`, `git`, `pytest`, `tectonic`) with `rtk`. Never prefix PowerShell cmdlets (`Get-ChildItem`, `Test-Path`, `Move-Item`, `Remove-Item`).
- **Candidate Data**: Ground truth is `profile-vault/candidate_profile.json` (falls back to `profile-vault/candidate_profile.example.json` if absent). Never fabricate credentials or change candidate facts.

---

## 2. Fast-Path Application Protocol (DO THIS FIRST)

When the user asks to "Create a resume for this" or provides a job alert (screenshot, image, Telegram/WhatsApp text, or URL):

### Step 1: Ingest & Execute Single Fast-Apply Command
Run `scripts/fast_apply.py` directly:

```powershell
# From raw pasted text or screenshot transcript:
rtk python scripts/fast_apply.py --text "Company - <Co>`nRole - <Title>`nBatch - 2026`nLocation - <Loc>`nRequirements: <Skills>" --artifact-dir "<active_brain_dir>"

# From a URL:
rtk python scripts/fast_apply.py "<job_url>" --artifact-dir "<active_brain_dir>"

# From a saved JSON file:
rtk python scripts/fast_apply.py "inbox/<job>.json" --artifact-dir "<active_brain_dir>"
```

### What `fast_apply.py` Handles Automatically:
1. **Field Extraction & Channel Detection**: Detects Email, Google Form, Career Portal, or Direct Referral.
2. **Fit Evaluation**: Computes 1.0–5.0 fit score and ATS rubric matching.
3. **LaTeX Tailoring**: Selects role template (`ai`, `data_engineering`, `data_analytics`, `sde`) and top 3 projects.
4. **Guaranteed 1-Page PDF**: Tectonic compile with iterative multi-stage compaction (`\linespread`, `itemsep`, margins). NEVER leaves a 2-page PDF.
5. **Channel Collateral**: Generates cover letter, ATS form answers, and submission checklist.
6. **Artifact Export**: Copies final PDF to active brain artifact directory for 1-click user download.
7. **Tracking**: Logs to SQLite (`profile-vault/jobs.db`) and Markdown tracker (`job_applications.md`).

**DO NOT** manually edit `.tex` files or run fragmented multi-step commands unless custom user adjustments are specifically requested.

---

## 3. Strict Quality & Structural Constraints
- **Application Directory Invariant**: Each application in `profile-vault/applications/<slug>/` MUST contain EXACTLY two files:
  - `resume.pdf` (tailored single-page PDF)
  - `application.md` (unified application package)
- **LaTeX Source Isolation**: The `.tex` file is cached under `profile-vault/cache/tex/<job_id>/resume.tex` (git-ignored). Never commit or leave `.tex` files inside `applications/`.
- **Single-Page Mandate**: A resume exceeding 1 page will fail `tests/test_oracle_hcm.py`.
- **Verification**: Run `rtk pytest -m "not live"` to verify the entire test suite passes.

---

## 4. Communication Style (Caveman Core)
- Start direct user replies with `"Suneeth, "`.
- Answer-first on Line 1.
- Provide clickable markdown file links (`[resume.pdf](file:///d:/...)`).
- Omit filler, greetings, and boilerplate.
- **Never emit `mailto:` or "One-Click Launch" links**: Provide clean recipient email, subject line, and copy-paste body only.
- **Subject Line Standard**: Use `Application: [Role] - [Candidate Name] (Immediate Joiner)`. Never include college name or graduation year in the subject header.

---

## 5. Public Repository & Open-Source Privacy Protocol
When releasing or syncing career-ops repositories publicly on GitHub:
- **Privacy Shield**: `.gitignore` MUST block `candidate_profile.json`, `portfolio_meta.json`, `applications/`, `certificates/`, `job_applications.md`, `inbox/`, `archive/`, and `.env*`.
- **Public Example Fallback**: Ship `candidate_profile.example.json` with generic placeholders. `tools/common.py` must fall back to `candidate_profile.example.json` if local candidate profile is missing.
- **Git History Expungement**: NEVER switch a repository from private to public if past commits contained `.env` or application cover letters. Always squash onto a fresh orphan `main` branch, force-push, and delete legacy branches before toggling visibility.
- **Author Attribution Invariant**: Audit and verify that all commit authors, licenses, and README footers belong solely to `Suneeth Reddy Peddamallu` (`Suneeth12`) with zero external or alternate account signatures.
