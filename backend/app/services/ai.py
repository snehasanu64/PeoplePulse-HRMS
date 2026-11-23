from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from backend.app.core.config import get_settings
from backend.app.schemas import (
    AssistantResponse,
    Candidate,
    InterviewEvaluation,
    ResumeScreenResult,
)


SKILL_ALIASES = {
    # Languages
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "c++": "C++",
    "c#": "C#",
    "golang": "Go",
    "ruby": "Ruby",
    "php": "PHP",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "scala": "Scala",
    "rust": "Rust",
    "matlab": "MATLAB",
    # Frontend
    "react native": "React Native",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "angular": "Angular",
    "vue": "Vue",
    "svelte": "Svelte",
    "html": "HTML",
    "css": "CSS",
    "sass": "Sass",
    "tailwind": "Tailwind CSS",
    "redux": "Redux",
    "webpack": "Webpack",
    "jest": "Jest",
    "accessibility": "Accessibility",
    "a11y": "Accessibility",
    "responsive ui": "Responsive UI",
    "responsive design": "Responsive UI",
    "component design": "Component Design",
    "performance optimization": "Performance Optimization",
    "api integration": "API Integration",
    "ui design": "UI Design",
    "ux research": "UX Research",
    "figma": "Figma",
    "wireframing": "Wireframing",
    "prototyping": "Prototyping",
    "design systems": "Design Systems",
    "user testing": "User Testing",
    "interaction design": "Interaction Design",
    "product thinking": "Product Thinking",
    # Backend
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "express": "Express",
    "spring boot": "Spring Boot",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "microservices": "Microservices",
    "system design": "System Design",
    "authentication": "Authentication",
    "authorization": "Authorization",
    "oauth": "OAuth",
    "jwt": "JWT",
    "grpc": "gRPC",
    "kafka": "Kafka",
    "message queues": "Message Queues",
    "celery": "Celery",
    "api design": "API Design",
    "cloud deployment": "Cloud Deployment",
    "serverless": "Serverless",
    # Data
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "spark": "Spark",
    "hadoop": "Hadoop",
    "airflow": "Airflow",
    "dbt": "dbt",
    "etl": "ETL",
    "data pipelines": "Data Pipelines",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "statistics": "Statistics",
    "data visualization": "Data Visualization",
    "tableau": "Tableau",
    "power bi": "Power BI",
    "predictive modeling": "Predictive Modeling",
    "nlp": "NLP",
    "computer vision": "Computer Vision",
    "experimentation": "Experimentation",
    "a/b testing": "A/B Testing",
    "data modeling": "Data Modeling",
    "business insights": "Business Insights",
    # DevOps and cloud
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "ci/cd": "CI/CD",
    "github actions": "GitHub Actions",
    "linux": "Linux",
    "bash": "Bash",
    "monitoring": "Monitoring",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "logging": "Logging",
    "observability": "Observability",
    "incident response": "Incident Response",
    "security": "Security",
    "scalability": "Scalability",
    "load balancing": "Load Balancing",
    "nginx": "Nginx",
    # QA
    "selenium": "Selenium",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "automation testing": "Automation Testing",
    "manual testing": "Manual Testing",
    "test cases": "Test Cases",
    "postman": "Postman",
    # Mobile
    "android": "Android",
    "ios": "iOS",
    "flutter": "Flutter",
    # Product, business and operations
    "product strategy": "Product Strategy",
    "roadmap": "Roadmap Planning",
    "user research": "User Research",
    "analytics": "Analytics",
    "stakeholder management": "Stakeholder Management",
    "agile": "Agile",
    "scrum": "Scrum",
    "jira": "Jira",
    "prioritization": "Prioritization",
    "prd": "PRD Writing",
    "go-to-market": "Go-to-Market",
    "project management": "Project Management",
    "leadership": "Leadership",
    "communication": "Communication",
    "process excellence": "Process Excellence",
    "risk tracking": "Risk Tracking",
    "business analysis": "Business Analysis",
    "requirements gathering": "Requirements Gathering",
    "salesforce": "Salesforce",
    "hubspot": "HubSpot",
    "crm": "CRM",
    "negotiation": "Negotiation",
    "pipeline management": "Pipeline Management",
    "customer success": "Customer Success",
    "account management": "Account Management",
    "seo": "SEO",
    "content marketing": "Content Marketing",
    "campaign management": "Campaign Management",
    "recruitment": "Recruitment",
    "onboarding": "Onboarding",
    "hr operations": "HR Operations",
    "payroll": "Payroll",
    "compliance": "Compliance",
    "excel": "Excel",
    "financial modeling": "Financial Modeling",
    "budgeting": "Budgeting",
    "forecasting": "Forecasting",
}

LAST_GEMINI_ERROR: str | None = None


def gemini_enabled() -> bool:
    key = str(get_settings().gemini_api_key or "").strip().strip('"').strip("'")
    return bool(key)


def gemini_last_error() -> str | None:
    return LAST_GEMINI_ERROR


def ask_gemini(prompt: str, *, temperature: float = 0.3) -> str | None:
    global LAST_GEMINI_ERROR
    settings = get_settings()
    api_key = str(settings.gemini_api_key or "").strip().strip('"').strip("'")
    if not api_key:
        LAST_GEMINI_ERROR = "GEMINI_API_KEY is missing from .env."
        return None

    models = []
    for model in [settings.gemini_model, "gemini-2.0-flash", "gemini-1.5-flash"]:
        model = str(model or "").strip()
        if model and model not in models:
            models.append(model)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    errors: list[str] = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                body = json.loads(response.read().decode("utf-8"))
            LAST_GEMINI_ERROR = None
            parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            answer = "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()
            if answer:
                return answer
            errors.append(f"{model}: empty Gemini response")
        except urllib.error.HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8", errors="replace"))
                message = error_body.get("error", {}).get("message") or str(exc)
                status = error_body.get("error", {}).get("status") or f"HTTP {exc.code}"
                errors.append(f"{model}: {status}: {message}")
                if status not in {"RESOURCE_EXHAUSTED", "NOT_FOUND"} and exc.code not in {404, 429}:
                    break
            except (json.JSONDecodeError, UnicodeDecodeError):
                errors.append(f"{model}: HTTP {exc.code}: Gemini request failed.")
                if exc.code not in {404, 429}:
                    break
        except urllib.error.URLError as exc:
            errors.append(f"{model}: Network error: {exc.reason}")
            break
        except (TimeoutError, json.JSONDecodeError):
            errors.append(f"{model}: Gemini response timed out or was not valid JSON.")
            break
    LAST_GEMINI_ERROR = " | ".join(errors) if errors else "Gemini request failed."
    return None


def parse_json_object(text: str | None) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    skills = set()
    for token, label in SKILL_ALIASES.items():
        if " " in token or not token.replace("+", "").replace("#", "").isalnum():
            matched = token in lowered
        else:
            matched = re.search(rf"(?<![\w+#]){re.escape(token)}(?![\w+#])", lowered) is not None
        if matched:
            skills.add(label)
    return sorted(skills)


def extract_resume_text(content: bytes, filename: str = "") -> str:
    """Pull readable text out of an uploaded PDF, DOCX or plain-text resume."""
    lower = (filename or "").lower()
    try:
        if content[:4] == b"%PDF" or lower.endswith(".pdf"):
            return _pdf_text(content)
        if content[:2] == b"PK" or lower.endswith(".docx"):
            return _docx_text(content)
    except Exception:
        pass
    return content.decode("utf-8", errors="ignore")


def _pdf_text(content: bytes) -> str:
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(pages).strip()
        if text:
            return text
    except Exception:
        pass
    return _pdf_text_fallback(content)


def _pdf_text_fallback(content: bytes) -> str:
    import zlib

    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, flags=re.DOTALL):
        raw = match.group(1).strip(b"\r\n")
        data = raw
        try:
            data = zlib.decompress(raw)
        except Exception:
            try:
                data = zlib.decompressobj().decompress(raw)
            except Exception:
                continue
        for text in re.findall(rb"\((?:\\.|[^\\()])*\)", data):
            cleaned = text[1:-1]
            cleaned = re.sub(rb"\\([()\\])", rb"\1", cleaned)
            chunks.append(cleaned.decode("latin-1", errors="ignore"))
    return " ".join(chunks)


def _docx_text(content: bytes) -> str:
    import html
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", " ", xml))


def resume_experience_years(text: str) -> int:
    matches = [int(value) for value in re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)", text.lower())]
    return min(max(matches), 30) if matches else 0


def resume_education(text: str) -> str:
    lowered = text.lower()
    for label, keys in (
        ("PhD", ("ph.d", "phd", "doctorate")),
        ("Master's degree", ("master", "m.tech", "mba", "m.sc", "ms in")),
        ("Bachelor's degree", ("bachelor", "b.tech", "b.e.", "b.sc", "bs in", "bca", "b.com")),
        ("Diploma", ("diploma", "associate degree")),
    ):
        if any(key in lowered for key in keys):
            return label
    return ""


def score_candidate(job_description: str, candidate: Candidate) -> ResumeScreenResult:
    required = set(extract_skills(job_description))
    supplied = {skill.strip() for skill in candidate.skills}
    matched = sorted(required & supplied)
    missing = sorted(required - supplied)
    coverage = len(matched) / max(len(required), 1)
    experience_bonus = min(max(candidate.experience_years, 0), 8) / 8
    education = str(candidate.education or "").strip()
    has_education = bool(education) and education.lower() not in {"not provided", "parsed from uploaded resume"}
    score = round((coverage * 72) + (experience_bonus * 20) + (8 if has_education else 0))

    if score >= 85:
        recommendation = "Strong hire signal. Move to structured technical interview."
    elif score >= 70:
        recommendation = "Promising profile. Validate missing skills during screening."
    else:
        recommendation = "Keep warm or route to a better-fit role."

    return ResumeScreenResult(
        candidate=candidate.name,
        match_score=min(score, 98),
        skills_matched=matched,
        missing_skills=missing,
        experience_analysis=(
            f"{candidate.experience_years} years mapped against role seniority."
            if candidate.experience_years
            else "No total years of experience could be detected in this resume."
        ),
        education_analysis=(
            f"{education} reviewed for baseline qualification."
            if has_education
            else "No formal education detail could be detected in this resume."
        ),
        recommendation=recommendation,
    )


def evaluate_interview(candidate_name: str, role: str, transcript: str, question: str = "") -> InterviewEvaluation:
    answer_parts = re.findall(r"Answer:\s*(.*?)(?=\n\s*Question\s+\d+:|\Z)", transcript, flags=re.IGNORECASE | re.DOTALL)
    answer_text = "\n".join(part.strip() for part in answer_parts if part.strip()) or transcript
    normalized = answer_text.lower()
    words = re.findall(r"[a-zA-Z]+", normalized)
    counts = Counter(words)
    answer_terms = set(extract_skills(answer_text))
    question_terms = set(extract_skills(question))
    relevant_terms = question_terms | set(extract_skills(role)) | {"FastAPI", "PostgreSQL", "System Design"}
    coverage = len(answer_terms & relevant_terms) / max(len(relevant_terms), 1)

    depth_terms = [
        "authentication",
        "authorization",
        "jwt",
        "oauth",
        "observability",
        "logging",
        "metrics",
        "tracing",
        "migration",
        "alembic",
        "database",
        "security",
        "testing",
        "rollback",
        "monitoring",
        "scalability",
        "tradeoff",
        "privacy",
        "audit",
    ]
    structure_terms = ["first", "then", "finally", "because", "tradeoff", "example", "measure", "validate"]
    confidence_terms = [
        "built",
        "implemented",
        "led",
        "designed",
        "deployed",
        "improved",
        "resolved",
        "use",
        "add",
        "enforce",
        "test",
        "document",
        "monitor",
        "review",
    ]

    depth_hits = sum(1 for term in depth_terms if term in normalized)
    structure_hits = sum(1 for term in structure_terms if term in normalized)
    confidence_hits = sum(counts[term] for term in confidence_terms)
    word_count = len(words)
    unique_ratio = len(set(words)) / max(word_count, 1)
    no_vowel_words = sum(1 for word in words if len(word) > 2 and not re.search(r"[aeiou]", word))
    gibberish_ratio = no_vowel_words / max(word_count, 1)

    quality_cap = 100
    if word_count < 8:
        quality_cap = 18
    elif word_count < 20:
        quality_cap = 35
    elif word_count < 45:
        quality_cap = 58
    elif coverage == 0 and depth_hits == 0:
        quality_cap = 62
    if unique_ratio < 0.35 or gibberish_ratio > 0.35:
        quality_cap = min(quality_cap, 25)

    gemini_json = parse_json_object(
        ask_gemini(
            "You are an HR technical interview evaluator. Return only valid JSON with keys "
            "technical_score, communication_score, confidence_score, transcript_summary, recommendation. "
            "Scores must be integers from 0 to 100. Very short, nonsense, repeated, or irrelevant answers "
            "must receive low scores. Keep summary and recommendation concise.\n\n"
            f"Candidate: {candidate_name}\nRole applied for: {role}\nQuestion set: {question}\n"
            f"Observed rubric data: word_count={word_count}, relevance_coverage={coverage:.2f}, "
            f"technical_depth_hits={depth_hits}, structure_hits={structure_hits}, ownership_hits={confidence_hits}, "
            f"quality_cap={quality_cap}.\nAnswer transcript: {answer_text}",
            temperature=0.2,
        )
    )
    if gemini_json:
        try:
            technical_score=max(0, min(quality_cap, int(gemini_json.get("technical_score", 0))))
            communication_score=max(0, min(quality_cap, int(gemini_json.get("communication_score", 0))))
            confidence_score=max(0, min(quality_cap, int(gemini_json.get("confidence_score", 0))))
            recommendation=str(gemini_json.get("recommendation") or "Review with the hiring panel.")
            if word_count < 20:
                recommendation = "Do not advance yet; the answer set is too brief to show interview readiness."
            return InterviewEvaluation(
                candidate_name=candidate_name,
                technical_score=technical_score,
                communication_score=communication_score,
                confidence_score=confidence_score,
                transcript_summary=str(gemini_json.get("transcript_summary") or "Gemini evaluated the interview response."),
                recommendation=recommendation,
            )
        except (TypeError, ValueError):
            pass

    technical_score = min(quality_cap, round(18 + coverage * 30 + min(depth_hits, 10) * 6 + min(word_count, 160) / 6))
    communication_score = min(quality_cap, round(24 + min(word_count, 160) / 4 + min(structure_hits, 6) * 6 + min(depth_hits, 5) * 2))
    confidence_score = min(quality_cap, round(16 + min(confidence_hits, 8) * 6 + min(depth_hits, 6) * 3 + (16 if word_count >= 60 else 0)))
    avg = round((technical_score + communication_score + confidence_score) / 3)

    if word_count < 20:
        recommendation = "Do not advance yet; the answer set is too brief to show interview readiness."
    elif avg >= 82:
        recommendation = "Advance to panel interview."
    elif avg >= 72:
        recommendation = "Continue with targeted follow-up questions."
    else:
        recommendation = "Request follow-up assessment before advancing."

    strongest = ", ".join(sorted(answer_terms & relevant_terms)) or "general communication"

    return InterviewEvaluation(
        candidate_name=candidate_name,
        technical_score=technical_score,
        communication_score=communication_score,
        confidence_score=confidence_score,
        transcript_summary=f"Evaluated {word_count} words for {role}. Strongest signal: {strongest}. Rubric checked relevance to the question, technical depth, answer structure, and evidence of hands-on ownership.",
        recommendation=recommendation,
    )


def answer_hr_question(role: str, message: str, context: dict[str, Any] | None = None) -> AssistantResponse:
    context = context or {}
    context_text = json.dumps(context, ensure_ascii=False)[:6000]
    gemini_answer = ask_gemini(
        "You are PeoplePulse's AI-powered HR Copilot for an HRMS. "
        "Behave like ChatGPT embedded inside PeoplePulse: friendly, professional, concise, and conversational. "
        "Use the provided HR context as the source of truth for personalized answers. "
        "If database_answer is present, preserve its facts and rewrite it naturally instead of replacing the numbers. "
        "Answer casual messages naturally. Do not sound like a database lookup tool. "
        "For career questions, give practical recommendations, skill gaps, and learning paths. "
        "For leave, payroll, attendance, and internal jobs, include a helpful next action suggestion when useful. "
        "For policy questions, explain clearly without inventing company rules outside the context. "
        "If the requested private data is not in context, say it is not available in the dashboard data.\n\n"
        f"Current role: {role}\n"
        f"HR context JSON: {context_text}\n"
        f"User question: {message}",
        temperature=0.35,
    )
    if gemini_answer:
        return AssistantResponse(answer=gemini_answer, actions=["Gemini response"])

    if context.get("database_answer"):
        return AssistantResponse(answer=str(context["database_answer"]), actions=[])

    text = message.lower()
    if any(word in text for word in ["hi", "hello", "hey", "wassup", "sup"]):
        return AssistantResponse(
            answer="Hey. I am doing well and ready to help with leave, payroll, attendance, career growth, internal jobs, or HR policies.",
            actions=[],
        )
    if "leave" in text:
        return AssistantResponse(
            answer="I can check leave balances and leave status from the live employee context. Ask me for your leave balance, leave history, or to apply leave with dates.",
            actions=[],
        )
    if "payroll" in text or "payslip" in text:
        return AssistantResponse(
            answer="I can explain payslip, salary, deductions, and latest net pay from the live payroll context. Ask me about your last salary or why a deduction was applied.",
            actions=[],
        )
    if "job description" in text or "interview question" in text:
        return AssistantResponse(
            answer="I can draft a competency-based job description and interview kit using role outcomes, required skills, and evaluation rubrics.",
            actions=[],
        )
    return AssistantResponse(
        answer="I am ready to help. Ask naturally about leave, attendance, payslip, performance, career growth, internal jobs, recruitment, policies, or HR actions.",
        actions=[],
    )
