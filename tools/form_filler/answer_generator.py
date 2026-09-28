from typing import Any, Dict, Optional

from tools.common import META_PATH, PROFILE_PATH, claimable_skills, classify_role, load_json
from tools.tailorer.latex_builder import education_facts

PROJECT_OUTCOMES = {
    "data_analytics": {
        "project_name": "Performance Analytics Dashboard & Reporting Pipeline",
        "challenging_aspect": "Visualizing and auditing 15,000+ transaction records across market territories using complex star-schema data models.",
        "timeline": "4 weeks from initial SQL data extraction to dashboard publish.",
        "impact": "Formulated custom DAX measures (Time-Intelligence, YoY Growth, Rolling Averages) and optimized star-schema SQL CTE queries to identify regional drop-offs and product line profitability trends.",
        "learning": "Pre-aggregating multi-table joins in SQL CTEs before loading into reporting tools significantly improves rendering speed.",
        "do_differently": "Implement automated daily incremental data refreshes from day one.",
    },
    "ai": {
        "project_name": "Enterprise Document Intelligence & Semantic Search Engine",
        "challenging_aspect": "Engineering multi-agent evaluation harness scoring hit-rate, response accuracy, and hallucination guardrails across vector embeddings.",
        "timeline": "4 weeks from vector retrieval design to production microservices.",
        "impact": "Architected end-to-end semantic retrieval system with FAISS embeddings and FastAPI microservices with automated evaluation benchmarks, maintaining sub-80ms latencies.",
        "learning": "Decoupling retrieval chunking from LLM generation guardrails yields higher accuracy and eliminates hallucination drift.",
        "do_differently": "Incorporate hybrid lexical (BM25) and dense vector search earlier in development.",
    },
    "sdet": {
        "project_name": "Automated Verification & Regression Testing Harness",
        "challenging_aspect": "Designing a comprehensive regression verification suite and schema validation pipeline ensuring zero regressions and strict compliance.",
        "timeline": "3 weeks from test architecture to 100% test pass rate.",
        "impact": "Implemented automated testing and verification algorithms that eliminated 100% of schema validation and compile-time regressions.",
        "learning": "Automating boundary condition checks and test isolation early prevents downstream regressions.",
        "do_differently": "Introduce property-based fuzz testing for unexpected schemas earlier.",
    },
    "product_management": {
        "project_name": "Application Operations & Performance Workflow Platform",
        "challenging_aspect": "Defining 0-to-1 product scope, user journey flows, and analytics dashboards across multiple platforms and metrics.",
        "timeline": "4 weeks from user requirement discovery to functional prototype.",
        "impact": "Delivered intuitive 0-to-1 workflow automating end-to-end tracking and metrics analysis, reducing manual effort by 85%.",
        "learning": "Focusing on core user friction points first creates high adoption before adding secondary features.",
        "do_differently": "Run structured user feedback interviews after the initial MVP release.",
    },
    "founders_office": {
        "project_name": "Autonomous Systems & Operational Automation Engine",
        "challenging_aspect": "Operating under high ambiguity to design 0-to-1 automated systems bridging workflows with production databases.",
        "timeline": "3 weeks from concept to working deployment.",
        "impact": "Built end-to-end autonomous pipeline reducing operational bottleneck by 90% while maintaining sub-80ms response latencies.",
        "learning": "Breaking complex operational bottlenecks into modular systems allows 10x faster execution.",
        "do_differently": "Set up automated telemetry dashboards from day one to monitor operational health.",
    },
    "default": {
        "project_name": "Distributed Asynchronous Task Queue & Job Scheduler",
        "challenging_aspect": "Engineering high-throughput asynchronous task processing handling 100,000+ daily jobs with priority queues, dead-letter routing, and retry policies.",
        "timeline": "4 weeks from architecture design to containerized deployment.",
        "impact": "Implemented persistent task states with PostgreSQL and Redis caching, achieving sub-10ms job dispatch and 99.9% uptime during load tests.",
        "learning": "Decoupling job ingestion from worker processing with dedicated Redis queues prevents API thread starvation under high concurrency.",
        "do_differently": "Set up automated distributed tracing with OpenTelemetry earlier during initial development.",
    },
}


class AnswerGenerator:
    """ATS application-form answers built from the JobPosting, candidate_profile.json and portfolio_meta.json."""

    def __init__(self, portfolio_meta_path: Optional[str] = None, candidate_profile_path: Optional[str] = None):
        self.meta = load_json(portfolio_meta_path or META_PATH)
        self.candidate_profile = load_json(candidate_profile_path or PROFILE_PATH)

    def generate(self, job_posting: Dict[str, Any]) -> Dict[str, Any]:
        job_posting = job_posting or {}
        profile, meta = self.candidate_profile, self.meta
        company = job_posting.get("company") or "your company"
        title = job_posting.get("title") or "this role"
        workplace_type = job_posting.get("workplace_type", "hybrid")
        sal = job_posting.get("salary_range") or {}
        currency, min_sal, max_sal = sal.get("currency", "INR"), sal.get("min", 0.0), sal.get("max", 0.0)

        exp_global = meta.get("expected_ctc_global", {"amount": 60000.0, "currency": "USD", "unit": "Annual"})
        exp_india = meta.get("expected_ctc_india", {"amount": 12.0, "currency": "INR", "unit": "LPA"})
        period = sal.get("period", "lpa")
        if currency == "USD" or workplace_type == "remote_worldwide":
            exp_ctc, curr_ctc = exp_global, {"amount": 0.0, "currency": "USD", "unit": "Annual"}
            if period == "monthly" and (min_sal > 0 or max_sal > 0):
                compensation = f"${int(min_sal):,} – ${int(max_sal):,} USD/month, aligned with posted role."
            else:
                compensation = (f"${int(min_sal):,} – ${int(max_sal):,} USD Annual (Base), aligned with posted role compensation."
                                if min_sal > 0 and max_sal > 0 else
                                f"${int(exp_global['amount']):,} USD Annual (Base), negotiable depending on equity and benefits.")
        else:
            exp_ctc, curr_ctc = exp_india, {"amount": 0.0, "currency": "INR", "unit": "LPA"}
            if period == "monthly" and (min_sal > 0 or max_sal > 0):
                compensation = f"₹{int(min_sal):,} – ₹{int(max_sal):,}/month (Stipend), aligned with posted role compensation." if min_sal > 0 and max_sal > 0 else f"₹{int(min_sal or max_sal):,}/month (Stipend), aligned with posted role compensation."
            else:
                compensation = (f"₹{min_sal:.1f} – ₹{max_sal:.1f} LPA INR, aligned with posted role compensation."
                                if min_sal > 0 and max_sal > 0 else
                                f"₹{exp_india['amount']:.1f} LPA INR (negotiable).")

        edu = education_facts(profile)
        first_edu = (profile.get("education") or [{}])[0]
        degree_info = f"{first_edu.get('degree', 'B.Tech')} at {edu['school']} (CGPA {edu['cgpa']}, {first_edu.get('graduation_year', '')} batch)"
        top_skills = ", ".join(claimable_skills(job_posting.get("skills_required"), profile))
        project = PROJECT_OUTCOMES.get(classify_role(title), PROJECT_OUTCOMES["default"])

        if workplace_type == "remote_worldwide":
            working_hours = ("Preferred working hours: 9:00 AM – 6:00 PM IST (UTC+5:30) with flexibility for overlap "
                             "with US EST / EU CET working windows (3:00 PM – 11:00 PM IST). Experienced in async remote collaboration.")
        else:
            working_hours = ("Standard working hours: 9:00 AM – 6:00 PM IST (UTC+5:30) or aligned with the company schedule. "
                             "Available for remote, hybrid, or relocation as required.")

        notice_days = meta.get("notice_period_days", 0)
        return {
            "job_id": job_posting.get("job_id", ""),
            "candidate_name": profile.get("full_name", ""),
            "candidate_email": profile.get("email", ""),
            "candidate_phone": profile.get("phone", ""),
            "education": degree_info,
            "linkedin_profile": profile.get("linkedin_url", ""),
            "salary_expectations": compensation,
            "base_compensation_usd": compensation,
            "availability_statement": f"Available to start {'immediately' if notice_days == 0 else f'in {notice_days} days'} upon offer confirmation.",
            "right_to_work_in_uk": "Open to UK remote work. Would require visa sponsorship for UK relocation.",
            "why_join_company": (f"I want to join {company} to contribute directly to engineering initiatives as a {title}, "
                                 "using rigorous machine learning and software engineering practices to solve demanding production challenges."),
            "search_motivation": (f"I selected the {title} position at {company} because my core engineering expertise in {top_skills} "
                                  "directly aligns with your team's technical challenges. Having built automated data ingestion pipelines "
                                  f"and containerized REST microservices, I am eager to apply that background at {company}."),
            "measurable_outcome_past_12m": (
                f"My top measurable engineering delivery in the past 12 months ({project['project_name']}):\n"
                f"• Challenging Aspect: {project['challenging_aspect']}\n"
                f"• Timeline: {project['timeline']}\n"
                f"• Final Outcome & Impact: {project['impact']}\n"
                f"• Learnings & Reflection: {project['learning']}\n"
                f"• What I Would Do Differently: {project['do_differently']}"),
            "job_search_timeline": f"Available with {notice_days} days notice period and actively interviewing.",
            "working_hours_and_timezone": working_hours,
            "reason_for_leaving": (f"I am completing my {degree_info} and seeking my next full-time opportunity as a {title} "
                                   "to build and scale production data systems and AI pipelines."),
            "notice_period_days": notice_days,
            "notice_period_radio": "Immediate Joiner / Less than 1 week" if notice_days <= 7 else f"{notice_days} days",
            "availability_status": meta.get("availability_status", "Immediate Joiner"),
            "current_ctc": curr_ctc,
            "expected_ctc": exp_ctc,
            "github_url": profile.get("github_url", ""),
            "portfolio_url": profile.get("portfolio_url", ""),
            "leetcode_profile": profile.get("leetcode_url", ""),
            "nats_registration_id": meta.get("nats_registration_id", ""),
        }
