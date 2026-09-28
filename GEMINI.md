# Antigravity Instructions: Profile Optimization & Career Ops

## Trigger Protocol: Resume Creation & Job Applications
Whenever the user:
- Uploads an image/screenshot of a job post (Telegram, LinkedIn, WhatsApp, Campus placement), OR
- Pastes a job description / referral text, OR
- Shares a job posting URL, OR
- Types: `"resume"`, `"create a resume for this"`, `"optimize resume"`, `"apply to this"`

### EXECUTE IMMEDIATELY (Single Fast-Path Pass):
Do NOT ask questions. Do NOT inspect templates manually. Do NOT write manual JSON files.
Run the unified `fast_apply.py` command:

```powershell
# 1. If text, screenshot transcript, or image:
rtk python scripts/fast_apply.py --text "Company - <Co>`nRole - <Title>`nBatch - 2026`nLocation - <Loc>`nRequirements: <Skills>" --artifact-dir "<active_brain_dir>"

# 2. If URL:
rtk python scripts/fast_apply.py "<job_url>" --artifact-dir "<active_brain_dir>"
```

### Response Mandate:
- **Line 1**: Direct link to the compiled 1-page PDF (`[<company>_resume.pdf](file:///...)`).
- **Line 2**: Clickable links to `resume.tex` and `application.md`.
- **Scannable Bullets**: Fit score (1.0–5.0), matched skills, and top 3 project highlights.
- **No `mailto:` or "One-Click Launch" links**: Provide clean recipient, subject line, and copy-paste email body only.
- **Subject Line Format**: `Application: [Role] - [Candidate Name] (Immediate Joiner)`. Do not include college or batch year in subject.
- **Strict Quality**: PDF must be strictly 1 page (guaranteed by `LaTeXBuilder` progressive auto-compactor).
