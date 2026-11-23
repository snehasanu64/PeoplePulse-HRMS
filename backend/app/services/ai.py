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
    "fastapi": "FastAPI",
    "python": "Python",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "microservices": "Microservices",
    "system design": "System Design",
    "rest": "REST APIs",
    "react": "React",
    "sql": "SQL",
    "aws": "AWS",
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


def analyze_attrition_with_gemini(employee_context: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not employee_context:
        return {
            "source": "Gemini",
            "model": get_settings().gemini_model,
            "counts": {"High": 0, "Medium": 0, "Low": 0},
            "employees": [],
            "insight": "No employee records were provided for attrition analysis.",
        }

    compact_context = [
        {
            "name": str(item.get("name") or "Unknown"),
            "role": str(item.get("role") or "Team Member"),
            "department": str(item.get("department") or item.get("dept") or "Unassigned"),
            "status": str(item.get("status") or "Active"),
            "performance": int(item.get("performance") or item.get("perf") or 0),
            "attendance": int(item.get("attendance") or 0),
            "sentiment": str(item.get("sentiment") or "Neutral"),
            "sentiment_updates": int(item.get("sentiment_updates") or 0),
            "task_status": str(item.get("task_status") or "Unknown"),
            "career_gap": str(item.get("career_gap") or "None"),
            "tenure_months": int(item.get("tenure_months") or 0),
        }
        for item in employee_context
    ]
    employee_names = {item["name"] for item in compact_context}
    gemini_json = parse_json_object(
        ask_gemini(
            "You are PeoplePulse's HR attrition risk analyst. Analyze the provided employees only. "
            "Use performance, attendance, daily sentiment, task completion, status, career gap, and tenure. "
            "Return only valid JSON with this exact shape: "
            '{"employees":[{"name":"Employee Name","risk":"High|Medium|Low","risk_score":0,'
            '"reasons":["reason 1","reason 2"],"recommendation":"manager action"}],'
            '"insight":"one concise workforce insight"}. '
            "risk_score must be an integer 0-100. High means immediate retention action, Medium means monitor, Low means stable. "
            "Do not invent employee names. Keep reasons short and explainable.\n\n"
            f"Employee data:\n{json.dumps(compact_context, ensure_ascii=False)}",
            temperature=0.15,
        )
    )
    if not gemini_json or not isinstance(gemini_json.get("employees"), list):
        return None

    results: list[dict[str, Any]] = []
    for item in gemini_json["employees"]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name not in employee_names:
            continue
        risk = str(item.get("risk") or "Low").title()
        if risk not in {"High", "Medium", "Low"}:
            risk = "Low"
        try:
            risk_score = max(0, min(100, int(item.get("risk_score", 0))))
        except (TypeError, ValueError):
            risk_score = {"High": 80, "Medium": 55, "Low": 20}[risk]
        reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
        results.append(
            {
                "name": name,
                "risk": risk,
                "risk_score": risk_score,
                "reasons": [str(reason)[:120] for reason in reasons[:3]],
                "recommendation": str(item.get("recommendation") or "Schedule a manager check-in.")[:220],
            }
        )

    by_name = {item["name"]: item for item in results}
    for item in compact_context:
        if item["name"] not in by_name:
            by_name[item["name"]] = {
                "name": item["name"],
                "risk": "Low",
                "risk_score": 20,
                "reasons": ["Gemini did not flag this employee."],
                "recommendation": "Continue normal manager check-ins.",
            }

    ordered = [by_name[item["name"]] for item in compact_context]
    counts = {
        "High": sum(1 for item in ordered if item["risk"] == "High"),
        "Medium": sum(1 for item in ordered if item["risk"] == "Medium"),
        "Low": sum(1 for item in ordered if item["risk"] == "Low"),
    }
    return {
        "source": "Gemini",
        "model": get_settings().gemini_model,
        "counts": counts,
        "employees": ordered,
        "insight": str(gemini_json.get("insight") or "Gemini analyzed attrition risk from connected HR data.")[:300],
    }


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    skills = set()
    for token, label in SKILL_ALIASES.items():
        if " " in token:
            matched = token in lowered
        else:
            matched = re.search(rf"\b{re.escape(token)}\b", lowered) is not None
        if matched:
            skills.add(label)
    return sorted(skills)


def score_candidate(job_description: str, candidate: Candidate) -> ResumeScreenResult:
    required = set(extract_skills(job_description))
    supplied = {skill.strip() for skill in candidate.skills}
    matched = sorted(required & supplied)
    missing = sorted(required - supplied)
    coverage = len(matched) / max(len(required), 1)
    experience_bonus = min(candidate.experience_years, 8) / 8
    score = round((coverage * 72) + (experience_bonus * 20) + (8 if candidate.education else 0))

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
        experience_analysis=f"{candidate.experience_years} years mapped against role seniority.",
        education_analysis=f"{candidate.education} reviewed for baseline qualification.",
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
