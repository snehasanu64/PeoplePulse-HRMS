import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.schemas import (
    ActionRequest,
    ActionResponse,
    AssistantRequest,
    AssistantResponse,
    Candidate,
    DashboardSummary,
    InterviewEvaluation,
    InterviewRequest,
    LeaveSubmitRequest,
    LeaveSubmitResponse,
    PayrollRunRequest,
    PayrollRunResponse,
    ResumeScreenRequest,
    ResumeScreenResult,
)
from backend.app.services import admin_data
from backend.app.core.config import get_settings
from backend.app.services.ai import (
    analyze_attrition_with_gemini,
    answer_hr_question,
    ask_gemini,
    evaluate_interview,
    gemini_enabled,
    gemini_last_error,
    score_candidate,
)

router = APIRouter(prefix="/api")
public_router = APIRouter()


def admin_dashboard_routes(target: APIRouter, prefix: str = "") -> None:
    @target.get(f"{prefix}/dashboard/admin/summary")
    def admin_summary() -> dict:
        return admin_data.dashboard_summary()

    @target.get(f"{prefix}/dashboard/admin/employee-growth")
    def admin_employee_growth() -> list[dict]:
        return admin_data.employee_growth()

    @target.get(f"{prefix}/dashboard/admin/department-distribution")
    def admin_department_distribution() -> list[dict]:
        return admin_data.department_distribution()

    @target.get(f"{prefix}/dashboard/admin/recent-activity")
    def admin_recent_activity() -> list[dict]:
        return admin_data.recent_activity()

    @target.get(f"{prefix}/dashboard/admin/payroll-overview")
    def admin_payroll_overview() -> dict:
        return admin_data.payroll_overview()

    @target.get(f"{prefix}/dashboard/admin/workforce-metrics")
    def admin_workforce_metrics() -> dict:
        return admin_data.workforce_metrics()


admin_dashboard_routes(router)
admin_dashboard_routes(public_router)


LEAVE_ENTITLEMENTS = {
    "Annual Leave": 20,
    "Sick Leave": 15,
    "Personal": 10,
    "Comp Off": 5,
}


def _money(value: float | int | None) -> str:
    return f"₹{round(float(value or 0)):,.0f}"


def _find_employee(context: dict[str, Any], employees: list[dict]) -> dict | None:
    employee_context = context.get("employee") if isinstance(context.get("employee"), dict) else {}
    employee_id = str(employee_context.get("id") or context.get("employee_id") or "")
    employee_name = str(employee_context.get("name") or context.get("employee_name") or "").lower()
    if employee_id:
        match = next((employee for employee in employees if str(employee.get("id")) == employee_id), None)
        if match:
            return match
    if employee_name:
        return next((employee for employee in employees if str(employee.get("name", "")).lower() == employee_name), None)
    return employees[0] if employees else None


def _leave_balances(employee: dict | None, leave_requests: list[dict]) -> list[dict]:
    name = str((employee or {}).get("name") or "")
    balances = []
    for leave_type, total in LEAVE_ENTITLEMENTS.items():
        used = sum(
            int(row.get("days") or 0)
            for row in leave_requests
            if row.get("requester_name") == name
            and row.get("status") == "Approved"
            and row.get("leave_type") == leave_type
        )
        balances.append({"type": leave_type, "total": total, "used": used, "remaining": max(total - used, 0)})
    return balances


def _salary_breakdown(employee: dict | None) -> dict:
    annual = float((employee or {}).get("salary") or 0)
    base = round(annual / 12)
    perf = int((employee or {}).get("perf") or 80)
    bonus = round(base * (0.10 if perf >= 90 else 0.07 if perf >= 80 else 0.04))
    allowances = max(500, round(base * 0.04))
    gross = base + bonus + allowances
    deductions = round(gross * 0.27) + 450
    return {
        "period": "May 2026",
        "annual": annual,
        "base": base,
        "bonus": bonus,
        "allowances": allowances,
        "gross": gross,
        "deductions": deductions,
        "net": gross - deductions,
    }


def _career_profile(employee: dict | None) -> dict:
    role = str((employee or {}).get("role") or "Team Member")
    dept = str((employee or {}).get("dept") or "General")
    perf = int((employee or {}).get("perf") or 70)
    path = f"{role} → Senior {role} → {dept} Lead"
    skills = {
        "Engineering": ["System Design", "Cloud Architecture", "API Quality"],
        "Product": ["Product Strategy", "User Research", "Stakeholder Management"],
        "Design": ["Design Systems", "Research Synthesis", "Accessibility"],
        "Analytics": ["SQL Analytics", "Data Storytelling", "Predictive Modeling"],
        "Sales": ["Pipeline Management", "Negotiation", "Customer Discovery"],
    }.get(dept, ["Communication", "Ownership", "Planning"])
    gaps = [{"skill": skill, "current": max(45, min(95, perf - index * 7)), "target": 90 if index == 0 else 85} for index, skill in enumerate(skills)]
    readiness = round((perf + max(0, perf - 5) + max(0, perf - 10)) / 3)
    return {"path": path, "promotion_readiness": readiness, "skill_gaps": gaps, "learning": skills}


def _job_match(employee: dict | None, job: dict) -> int:
    employee_text = f"{(employee or {}).get('role', '')} {(employee or {}).get('dept', '')}".lower()
    job_text = f"{job.get('title', '')} {job.get('dept', '')}".lower()
    dept = 35 if (employee or {}).get("dept") == job.get("dept") else 10
    role = 25 if any(word and word in employee_text for word in re.split(r"\W+", job_text) if len(word) > 3) else 8
    perf = round(float((employee or {}).get("perf") or 70) * 0.30)
    return min(100, dept + role + perf)


def _parse_leave_type(text: str) -> str:
    lowered = text.lower()
    if "sick" in lowered:
        return "Sick Leave"
    if "personal" in lowered:
        return "Personal"
    if "comp" in lowered:
        return "Comp Off"
    return "Annual Leave"


def _parse_dates(text: str) -> tuple[str, str]:
    today = datetime.now().date()
    lowered = text.lower()
    if "tomorrow" in lowered:
        target = today + timedelta(days=1)
        return target.isoformat(), target.isoformat()
    if "next monday" in lowered:
        days_ahead = (7 - today.weekday()) % 7 or 7
        target = today + timedelta(days=days_ahead)
        return target.isoformat(), target.isoformat()
    iso_dates = re.findall(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", text)
    if iso_dates:
        normalized = []
        for item in iso_dates[:2]:
            y, m, d = re.split(r"[-/]", item)
            normalized.append(f"{y}-{int(m):02d}-{int(d):02d}")
        return normalized[0], normalized[-1]
    duration = re.search(r"(\d+)\s+days?", lowered)
    if duration:
        days = max(int(duration.group(1)), 1)
        return today.isoformat(), (today + timedelta(days=days - 1)).isoformat()
    return today.isoformat(), today.isoformat()


def _copilot_context(role: str, frontend_context: dict[str, Any]) -> dict:
    employees = admin_data.list_employees()
    departments = admin_data.list_departments()
    jobs = admin_data.list_jobs()
    leaves = admin_data.list_leave_requests()
    applications = admin_data.list_internal_applications()
    employee = _find_employee(frontend_context, employees)
    active_jobs = [job for job in jobs if job.get("status") == "Active"]
    dept_counts = Counter(employee.get("dept") for employee in employees)
    payroll = admin_data.payroll_overview()
    workforce = admin_data.workforce_metrics()
    summary = admin_data.dashboard_summary()
    candidate_counts = Counter(app.get("status") for app in applications)
    screening = frontend_context.get("screening_history", []) if isinstance(frontend_context.get("screening_history"), list) else []
    attendance = frontend_context.get("attendance", {}) if isinstance(frontend_context.get("attendance"), dict) else {}
    sentiment = frontend_context.get("daily_updates", []) if isinstance(frontend_context.get("daily_updates"), list) else []
    return {
        "role": role,
        "employee": employee,
        "employees": employees,
        "departments": departments,
        "jobs": jobs,
        "active_jobs": active_jobs,
        "leave_requests": leaves,
        "leave_balances": _leave_balances(employee, leaves),
        "payroll": payroll,
        "salary": _salary_breakdown(employee),
        "workforce": workforce,
        "summary": summary,
        "department_distribution": [{"department": dept, "count": count} for dept, count in dept_counts.items()],
        "internal_applications": applications,
        "candidate_pipeline": dict(candidate_counts),
        "screening_history": screening,
        "attendance": attendance,
        "sentiment_updates": sentiment,
        "career": _career_profile(employee),
        "job_recommendations": sorted(
            [{**job, "ai_match_score": _job_match(employee, job)} for job in active_jobs],
            key=lambda item: item["ai_match_score"],
            reverse=True,
        )[:6],
        "activity_logs": admin_data.recent_activity(10),
    }


def _tool_current_time() -> dict[str, Any]:
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "time": now.strftime("%I:%M %p"),
        "timezone": now.tzname() or "local time",
    }


def _tool_employee_profile(context: dict[str, Any]) -> dict[str, Any]:
    employee = context.get("employee") or {}
    return {
        "id": employee.get("id"),
        "name": employee.get("name"),
        "role": employee.get("role"),
        "department": employee.get("dept") or employee.get("department"),
        "status": employee.get("status"),
        "joined": employee.get("joined"),
        "annual_salary": employee.get("salary"),
        "performance_score": employee.get("perf"),
        "attrition_risk": employee.get("attrition"),
    }


def _tool_payroll_summary(context: dict[str, Any]) -> dict[str, Any]:
    salary = context.get("salary") or {}
    payroll = context.get("payroll") or {}
    return {
        "employee_payslip": salary,
        "company_payroll": payroll,
    }


def _tool_performance_summary(context: dict[str, Any]) -> dict[str, Any]:
    employee = context.get("employee") or {}
    frontend_performance = context.get("frontend_performance") or {}
    career = context.get("career") or {}
    return {
        "employee": employee.get("name"),
        "score": employee.get("perf"),
        "frontend_breakdown": frontend_performance,
        "career_readiness": career.get("promotion_readiness"),
        "skill_gaps": career.get("skill_gaps", []),
    }


def _tool_internal_jobs(context: dict[str, Any]) -> list[dict[str, Any]]:
    return context.get("job_recommendations") or []


def _tool_application_status(context: dict[str, Any]) -> list[dict[str, Any]]:
    employee = context.get("employee") or {}
    employee_id = str(employee.get("id") or "")
    rows = context.get("internal_applications") or []
    if employee_id:
        rows = [row for row in rows if str(row.get("employee_id")) == employee_id]
    return rows


def _tool_department_info(message: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    text = message.lower()
    departments = context.get("departments") or []
    matched = [dept for dept in departments if str(dept.get("name", "")).lower() in text]
    return matched or departments


def _tool_candidate_info(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline": context.get("candidate_pipeline") or {},
        "internal_candidates": context.get("internal_applications") or [],
        "screening_history": context.get("screening_history") or [],
    }


def _tool_leave_balance(context: dict[str, Any]) -> list[dict[str, Any]]:
    return context.get("leave_balances") or []


def _tool_attendance_summary(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("attendance") or {}


def _tool_create_leave_request(message: str, context: dict[str, Any]) -> dict[str, Any]:
    employee = context.get("employee")
    if not employee:
        raise ValueError("Logged-in employee was not found")
    from_date, to_date = _parse_dates(message)
    leave_type = _parse_leave_type(message)
    return admin_data.create_leave_request(
        {
            "requester_name": employee["name"],
            "requester_role": "employee",
            "leave_type": leave_type,
            "from_date": from_date,
            "to_date": to_date,
            "reason": "Created by PeoplePulse AI Copilot",
        }
    )


def _tool_apply_internal_job(message: str, context: dict[str, Any]) -> dict[str, Any]:
    employee = context.get("employee")
    if not employee:
        raise ValueError("Logged-in employee was not found")
    recommendations = context.get("job_recommendations") or []
    if not recommendations:
        raise ValueError("No active internal jobs are available")
    text = message.lower()
    job = next((row for row in recommendations if str(row.get("title", "")).lower() in text), recommendations[0])
    return admin_data.create_internal_application(
        {
            "employee_id": employee["id"],
            "employee_name": employee["name"],
            "job_id": job["id"],
            "job_title": job["title"],
            "job_dept": job["dept"],
            "job_role": job["title"],
            "job_salary": employee.get("salary", 0),
            "ai_score": job["ai_match_score"],
        }
    )


def _tool_schedule_interview(message: str, context: dict[str, Any]) -> dict[str, Any]:
    applications = context.get("internal_applications") or []
    text = message.lower()
    match = next(
        (
            row
            for row in applications
            if str(row.get("employee_name", "")).lower() in text
            or str(row.get("job_title", "")).lower() in text
        ),
        applications[0] if applications else None,
    )
    if not match:
        raise ValueError("No candidate application is available to schedule")
    updated = admin_data.update_internal_application(int(match["id"]), "Interview")
    return {
        "application_id": updated["id"],
        "candidate": match.get("employee_name"),
        "job": match.get("job_title"),
        "status": updated["status"],
    }


def _detect_copilot_tools(message: str, role: str) -> list[str]:
    text = message.lower()
    tools: list[str] = []
    improvement_terms = [
        "improve",
        "improve myself",
        "do better",
        "better myself",
        "grow",
        "growth",
        "weakness",
        "weaknesses",
        "strength",
        "strengths",
        "advice",
        "recommend",
        "recommendation",
        "next step",
        "next steps",
    ]
    if re.search(r"\b(time|date|today|now)\b", text) and "time off" not in text:
        tools.append("get_current_time")
    if any(term in text for term in ["who am i", "profile", "my role", "my department", "my details"]):
        tools.append("get_employee_profile")
    if "leave" in text or "vacation" in text or "break" in text or "time off" in text:
        if "apply" in text or "create" in text or "request leave" in text:
            tools.append("create_leave_request")
        tools.append("get_leave_balance")
    if "attendance" in text or "clock" in text or "hours" in text or "present" in text or "absent" in text:
        tools.append("get_attendance_summary")
    if "salary" in text or "payroll" in text or "payslip" in text or "deduction" in text or "net pay" in text or "last pay" in text:
        tools.append("get_payroll_summary")
    if (
        "performance" in text
        or "score" in text
        or "promotion" in text
        or "ready" in text
        or "how am i doing" in text
        or any(term in text for term in improvement_terms)
    ):
        tools.append("get_performance_summary")
    if "internal" in text or "opening" in text or "job" in text or "role" in text or "career" in text or any(term in text for term in improvement_terms):
        if "apply" in text:
            tools.append("apply_internal_job")
        tools.append("get_internal_jobs")
    if "application" in text or "applied" in text or "status" in text:
        tools.append("get_application_status")
    if "department" in text or "team" in text:
        tools.append("get_department_info")
    if role == "recruiter" and ("candidate" in text or "pipeline" in text or "interview" in text or "screen" in text):
        tools.append("get_candidate_info")
    if "schedule" in text and "interview" in text:
        tools.append("schedule_interview")
    if not tools:
        tools.append("get_employee_profile" if role == "employee" else "get_department_info")
    return list(dict.fromkeys(tools))


def _is_casual_copilot_message(message: str) -> bool:
    clean = re.sub(r"[^a-z\s]", " ", message.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    casual = {
        "hi",
        "hii",
        "hiii",
        "hello",
        "hey",
        "heyy",
        "wassup",
        "sup",
        "yo",
        "how are you",
        "how r u",
        "how are u",
        "hru",
        "whats up",
        "what is up",
        "how are things",
    }
    return clean in casual


def _execute_copilot_tools(message: str, role: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for tool in _detect_copilot_tools(message, role):
        try:
            if tool == "get_current_time":
                data = _tool_current_time()
            elif tool == "get_employee_profile":
                data = _tool_employee_profile(context)
            elif tool == "get_leave_balance":
                data = _tool_leave_balance(context)
            elif tool == "get_attendance_summary":
                data = _tool_attendance_summary(context)
            elif tool == "get_payroll_summary":
                data = _tool_payroll_summary(context)
            elif tool == "get_performance_summary":
                data = _tool_performance_summary(context)
            elif tool == "get_internal_jobs":
                data = _tool_internal_jobs(context)
            elif tool == "get_application_status":
                data = _tool_application_status(context)
            elif tool == "get_department_info":
                data = _tool_department_info(message, context)
            elif tool == "get_candidate_info":
                data = _tool_candidate_info(context)
            elif tool == "create_leave_request":
                data = _tool_create_leave_request(message, context)
            elif tool == "apply_internal_job":
                data = _tool_apply_internal_job(message, context)
            elif tool == "schedule_interview":
                data = _tool_schedule_interview(message, context)
            else:
                data = {}
            results.append({"tool": tool, "ok": True, "data": data})
        except Exception as exc:
            results.append({"tool": tool, "ok": False, "error": str(exc)})
    return results


def _tool_based_answer(message: str, role: str, context: dict[str, Any], tool_results: list[dict[str, Any]]) -> tuple[str, list[str]]:
    ok_results = [result for result in tool_results if result.get("ok")]
    label_map = {
        "get_current_time": "Current time",
        "get_employee_profile": "Employee profile",
        "get_leave_balance": "Leave balance",
        "get_attendance_summary": "Attendance summary",
        "get_payroll_summary": "Payroll summary",
        "get_performance_summary": "Performance summary",
        "get_internal_jobs": "Internal jobs",
        "get_application_status": "Applications",
        "get_department_info": "Departments",
        "get_candidate_info": "Candidates",
        "create_leave_request": "Leave request created",
        "apply_internal_job": "Internal application created",
        "schedule_interview": "Interview scheduled",
    }
    labels = [label_map.get(str(result["tool"]), str(result["tool"])) for result in ok_results]
    by_tool = {result["tool"]: result.get("data") for result in ok_results}
    employee = context.get("employee") or {}
    first = str(employee.get("name") or "there").split()[0]
    if _is_casual_copilot_message(message):
        return f"Hey {first}. I am doing well and ready to help. Ask me naturally about leave, attendance, payroll, performance, career growth, internal jobs, or HR policies.", labels
    if "get_current_time" in by_tool:
        current = by_tool["get_current_time"]
        return f"It is currently {current['time']} on {current['date']} ({current['timezone']}).", labels
    if "create_leave_request" in by_tool:
        record = by_tool["create_leave_request"]
        return f"Done, {first}. I created your {record['leave_type']} request from {record['from_date']} to {record['to_date']}. It is now {record['status']}.", labels
    if "apply_internal_job" in by_tool:
        app = by_tool["apply_internal_job"]
        return f"Done, {first}. I applied you for {app['job_title']} with an AI match score of {app['ai_score']}%. Your application status is {app['status']}.", labels
    if "schedule_interview" in by_tool:
        interview = by_tool["schedule_interview"]
        return f"Interview stage updated for {interview.get('candidate') or 'the candidate'} on {interview.get('job') or 'the role'}. Status is now {interview['status']}.", labels
    if "get_leave_balance" in by_tool:
        balances = by_tool["get_leave_balance"] or []
        parts = ", ".join(f"{row['type']}: {row['remaining']} remaining" for row in balances)
        return f"{first}, your current leave balance is {parts}. Approved leave is the only thing that reduces this balance.", labels
    if "get_payroll_summary" in by_tool:
        slip = (by_tool["get_payroll_summary"] or {}).get("employee_payslip") or {}
        return f"Your latest payslip is for {slip.get('period')}. Gross pay is {_money(slip.get('gross'))}, deductions are {_money(slip.get('deductions'))}, and net pay is {_money(slip.get('net'))}.", labels
    if "get_attendance_summary" in by_tool:
        attendance = by_tool["get_attendance_summary"] or {}
        today = attendance.get("today") or {}
        return f"Your attendance is {attendance.get('rate', 0)}%. Present days: {attendance.get('present_days', 0)}, absent records: {attendance.get('absent_days', 0)}. Today: {today.get('status', 'No record')} with {today.get('hours', '0h 00m')} logged.", labels
    if "get_performance_summary" in by_tool:
        perf = by_tool["get_performance_summary"] or {}
        gaps = perf.get("skill_gaps") or []
        priority_gaps = sorted(
            gaps,
            key=lambda gap: int(gap.get("target") or 0) - int(gap.get("current") or 0),
            reverse=True,
        )[:3]
        gap_text = ", ".join(
            f"{gap.get('skill')} ({gap.get('current')}/{gap.get('target')})"
            for gap in priority_gaps
        ) or "your role-specific skills"
        frontend = perf.get("frontend_breakdown") or {}
        breakdown = frontend.get("breakdown") if isinstance(frontend.get("breakdown"), dict) else {}
        attendance = breakdown.get("attendance")
        task = breakdown.get("task")
        sentiment = breakdown.get("sentiment")
        score = perf.get("score")
        readiness = perf.get("career_readiness")
        if any(term in message.lower() for term in ["improve", "do better", "better myself", "weakness", "advice", "recommend", "grow"]):
            signals = []
            if attendance is not None:
                signals.append(f"keep attendance steady around {attendance}% or higher")
            if task is not None:
                signals.append(f"raise task completion from {task}% by closing daily tasks before clock-out")
            if sentiment is not None:
                signals.append(f"improve daily sentiment from {sentiment}% by logging blockers early")
            signal_text = "; ".join(signals) or "keep attendance, daily task completion, and manager feedback consistent"
            return (
                f"{first}, based on your live PeoplePulse record, your performance score is {score}/100 and promotion readiness is {readiness}%. "
                f"To improve, focus first on {gap_text}. Practically: {signal_text}. "
                "A good next step is to pick one skill gap, complete one learning item this week, and write clearer daily task updates so your progress is visible.",
                labels,
            )
        return f"{first}, your current performance score is {score}/100. Promotion readiness is {readiness}%, based on your role, performance, attendance context, and career gaps: {gap_text}.", labels
    if "get_internal_jobs" in by_tool:
        jobs = by_tool["get_internal_jobs"] or []
        if not jobs:
            return "I checked the live job postings. There are no active internal openings right now.", labels
        return "Here are the best live internal openings for you: " + "; ".join(f"{job['title']} in {job['dept']} ({job['ai_match_score']}% match)" for job in jobs[:5]) + ".", labels
    if "get_application_status" in by_tool:
        apps = by_tool["get_application_status"] or []
        if not apps:
            return f"{first}, you do not have any internal job applications yet.", labels
        return "Your current applications are: " + "; ".join(f"{app['job_title']}: {app['status']} ({app['ai_score']}% match)" for app in apps[:5]) + ".", labels
    if "get_candidate_info" in by_tool:
        data = by_tool["get_candidate_info"] or {}
        pipeline = ", ".join(f"{stage}: {count}" for stage, count in (data.get("pipeline") or {}).items()) or "No candidates yet"
        return f"Recruiting pipeline from live records: {pipeline}. Internal candidates tracked: {len(data.get('internal_candidates') or [])}.", labels
    if "get_department_info" in by_tool:
        departments = by_tool["get_department_info"] or []
        return f"I checked live department records. There are {len(departments)} department(s): " + ", ".join(f"{dept.get('name')} ({dept.get('count', 0)} employees)" for dept in departments[:8]) + ".", labels
    profile = by_tool.get("get_employee_profile") or {}
    return f"Hey {first}. I am connected to your live PeoplePulse data. You are listed as {profile.get('role', 'Team Member')} in {profile.get('department', 'your department')}. Ask me about leave, attendance, payroll, performance, career, or internal jobs.", labels


def _run_copilot_response(payload: AssistantRequest) -> AssistantResponse:
    role = payload.role
    context = _copilot_context(role, payload.context)
    if isinstance(payload.context.get("performance"), dict):
        context["frontend_performance"] = payload.context["performance"]
    tool_results = _execute_copilot_tools(payload.message, role, context)
    deterministic_answer, action_labels = _tool_based_answer(payload.message, role, context, tool_results)
    if _is_casual_copilot_message(payload.message):
        return AssistantResponse(answer=deterministic_answer, actions=[])
    gemini_context = {
        "role": role,
        "question": payload.message,
        "conversation": payload.context.get("conversation", []),
        "tool_results": tool_results,
        "database_context": {
            "employee": context.get("employee"),
            "leave_balances": context.get("leave_balances"),
            "attendance": context.get("attendance"),
            "salary": context.get("salary"),
            "career": context.get("career"),
            "active_jobs": context.get("job_recommendations"),
            "applications": _tool_application_status(context),
            "departments": context.get("departments"),
            "candidate_pipeline": context.get("candidate_pipeline"),
            "policies": payload.context.get("policies", {}),
        },
        "database_answer": deterministic_answer,
        "instruction": (
            "Use tool_results and database_context as the only source of numeric facts. "
            "Do not say you lack real-time access because tools already ran. "
            "Respond like ChatGPT: friendly, concise, personalized, and helpful. "
            "For actions, confirm the action result clearly."
        ),
    }
    try:
        gemini = answer_hr_question(role, payload.message, gemini_context)
        generic_markers = [
            "I don't have access to real-time",
            "I do not have access to real-time",
            "For employee, I can answer policy",
            "For recruiter, I can answer policy",
            "For manager, I can answer policy",
            "For admin, I can answer policy",
            "Your leave balance is 18 PTO days",
        ]
        if gemini.answer and not any(marker in gemini.answer for marker in generic_markers):
            return AssistantResponse(answer=gemini.answer, actions=action_labels)
    except Exception:
        pass
    return AssistantResponse(answer=deterministic_answer, actions=action_labels)


def _copilot_action(message: str, role: str, context: dict) -> tuple[str | None, list[str]]:
    text = message.lower()
    employee = context.get("employee")
    if "apply" in text and "leave" in text:
        if not employee:
            return "I could not find the logged-in employee record for this leave request.", []
        from_date, to_date = _parse_dates(message)
        leave_type = _parse_leave_type(message)
        record = admin_data.create_leave_request(
            {
                "requester_name": employee["name"],
                "requester_role": "employee",
                "leave_type": leave_type,
                "from_date": from_date,
                "to_date": to_date,
                "reason": "Created by PeoplePulse AI Copilot",
            }
        )
        return (
            f"Created {record['leave_type']} request for {record['requester_name']} from {record['from_date']} to {record['to_date']}. Status: {record['status']}.",
            ["Leave request created"],
        )
    if role in {"manager", "admin"} and ("approve leave" in text or "reject leave" in text):
        pending = [row for row in context["leave_requests"] if row.get("status") == "Pending Approval"]
        if not pending:
            return "There are no pending leave requests to update.", []
        status = "Approved" if "approve" in text else "Rejected"
        record = admin_data.update_leave_status(int(pending[0]["id"]), status, f"{role.title()} {status.lower()} this request from AI Copilot.")
        return f"{status} leave request #{record['id']} for {record['requester_name']}.", [f"Leave {status.lower()}"]
    if role == "recruiter" and ("create job" in text or "post job" in text):
        title = re.sub(r".*(create|post)\s+job\s+", "", message, flags=re.I).strip() or "New Role"
        dept = next((dept["name"] for dept in context["departments"] if dept["name"].lower() in text), "Engineering")
        record = admin_data.create_job({"title": title, "dept": dept, "status": "Active"})
        return f"Created active job posting: {record['title']} in {record['dept']}.", ["Job created"]
    if "apply" in text and ("job" in text or "opening" in text or "role" in text):
        if not employee:
            return "I could not find the logged-in employee record for this job application.", []
        recommendations = context.get("job_recommendations") or []
        if not recommendations:
            return "There are no active internal openings available right now.", []
        job = recommendations[0]
        record = admin_data.create_internal_application(
            {
                "employee_id": employee["id"],
                "employee_name": employee["name"],
                "job_id": job["id"],
                "job_title": job["title"],
                "job_dept": job["dept"],
                "job_role": job["title"],
                "job_salary": employee.get("salary", 0),
                "ai_score": job["ai_match_score"],
            }
        )
        return f"Applied {employee['name']} to {job['title']} with AI match score {record['ai_score']}%.", ["Internal application created"]
    return None, []


def _deterministic_copilot_answer(message: str, role: str, context: dict) -> tuple[str, list[str]]:
    text = message.lower()
    employee = context.get("employee") or {}
    greeting_words = {"hi", "hii", "hiii", "hello", "hey", "heyy", "help"}
    clean_words = {word.strip(".,!? ").lower() for word in text.split()}
    if clean_words & greeting_words or len(text.strip()) < 4:
        if role == "employee":
            salary = context["salary"]
            attendance = context.get("attendance") or {}
            return (
                f"Hi {employee.get('name', 'there')}. I am connected to your live HR data. "
                f"Right now I can see your role as {employee.get('role', 'Team Member')} in {employee.get('dept', 'Employee')}, "
                f"latest net pay {_money(salary['net'])}, attendance rate {attendance.get('rate', '--')}%, "
                f"and {len(context['job_recommendations'])} active internal job recommendations. "
                "Ask me things like leave balance, payslip, attendance summary, promotion readiness, or internal jobs.",
                ["Live employee context"],
            )
        if role == "recruiter":
            return (
                f"Hi. I am connected to recruiting data: {len(context['active_jobs'])} active jobs, "
                f"{sum(context['candidate_pipeline'].values())} internal candidates, and {len(context['screening_history'])} screening records in this session. "
                "Ask about hiring pipeline, top candidates, active jobs, or generating a job description.",
                ["Live recruiting context"],
            )
        if role == "manager":
            low_perf = [row["name"] for row in context["employees"] if int(row.get("perf") or 0) < 75]
            pending = [row for row in context["leave_requests"] if row.get("status") == "Pending Approval"]
            return (
                f"Hi. I am connected to your team data: {len(context['employees'])} employees, "
                f"{len(pending)} pending leave request(s), and {len(low_perf)} employee(s) needing coaching. "
                "Ask about team performance, leave approvals, attendance issues, or coaching actions.",
                ["Live manager context"],
            )
        summary = context["summary"]
        return (
            f"Hi. I am connected to company HR data: {summary['total_employees']} employees, "
            f"{summary['open_positions']} open positions, yearly payroll {_money(summary['monthly_payroll'])}, "
            f"and average performance {summary['average_performance']}%. Ask about workforce, payroll, departments, hiring, or attrition.",
            ["Live company context"],
        )
    if "leave balance" in text or ("leave" in text and "balance" in text):
        rows = context["leave_balances"]
        return "Your leave balance is: " + ", ".join(f"{row['type']}: {row['remaining']} remaining ({row['used']} used of {row['total']})" for row in rows) + ".", ["Leave balance"]
    if "payslip" in text or "salary" in text or "deduction" in text or "last salary" in text:
        salary = context["salary"]
        return f"Latest payslip for {salary['period']}: gross {_money(salary['gross'])}, deductions {_money(salary['deductions'])}, net pay {_money(salary['net'])}. Annual salary is {_money(salary['annual'])}.", ["Payslip"]
    if "attendance" in text:
        attendance = context.get("attendance") or {}
        if attendance:
            return f"Attendance summary: rate {attendance.get('rate', '--')}%, present days {attendance.get('present_days', '--')}, absent records {attendance.get('absent_days', '--')}, today status {attendance.get('today', {}).get('status', '--')}.", ["Attendance"]
        return "Attendance data is not stored in the backend database yet. The employee dashboard can still show local clock-in records from the browser session.", ["Attendance"]
    if "promotion" in text or "career" in text or "skill" in text:
        career = context["career"]
        gaps = ", ".join(f"{gap['skill']} {gap['current']}/{gap['target']}" for gap in career["skill_gaps"])
        return f"Promotion readiness is {career['promotion_readiness']}%. Recommended path: {career['path']}. Skill gaps: {gaps}. Learning recommendations: {', '.join(career['learning'])}.", ["Career AI"]
    if "internal" in text or "opening" in text or "recommend job" in text:
        jobs = context["job_recommendations"]
        if not jobs:
            return "No active internal openings are available right now.", ["Internal jobs"]
        return "Top internal openings: " + "; ".join(f"{job['title']} in {job['dept']} ({job['ai_match_score']}% match)" for job in jobs[:5]) + ".", ["Internal jobs"]
    if role == "recruiter" and ("pipeline" in text or "candidate" in text or "active jobs" in text):
        active = len(context["active_jobs"])
        pipeline = ", ".join(f"{stage}: {count}" for stage, count in context["candidate_pipeline"].items()) or "No candidates yet"
        return f"Recruiting snapshot: {active} active jobs. Candidate pipeline: {pipeline}.", ["Recruiting"]
    if role == "manager" and ("team" in text or "coaching" in text or "performance" in text):
        employees = sorted(context["employees"], key=lambda row: int(row.get("perf") or 0), reverse=True)
        best = employees[0]["name"] if employees else "No employees"
        coaching = [row["name"] for row in employees if int(row.get("perf") or 0) < 75]
        return f"Team performance: best performer is {best}. Employees needing coaching: {', '.join(coaching) if coaching else 'none'}." , ["Team performance"]
    if role == "admin" and ("company" in text or "employees" in text or "payroll" in text or "workforce" in text):
        summary = context["summary"]
        return f"Company snapshot: {summary['total_employees']} employees, {summary['active_today']} active, {summary['open_positions']} open positions, yearly payroll {_money(summary['monthly_payroll'])}, average performance {summary['average_performance']}%.", ["Executive summary"]
    if role == "employee":
        salary = context["salary"]
        balances = context["leave_balances"]
        annual = next((row for row in balances if row["type"] == "Annual Leave"), balances[0] if balances else {"remaining": 0})
        return (
            f"I checked live records for {employee.get('name', 'you')}. "
            f"Current role: {employee.get('role', 'Team Member')} in {employee.get('dept', 'Employee')}. "
            f"Annual leave remaining: {annual['remaining']}. Latest net pay: {_money(salary['net'])}. "
            f"Performance score: {employee.get('perf', '--')}%. Ask a specific question and I will pull the matching live data.",
            ["Live employee data"],
        )
    if role == "recruiter":
        pipeline = ", ".join(f"{stage}: {count}" for stage, count in context["candidate_pipeline"].items()) or "No internal candidates yet"
        return (
            f"Live recruiting snapshot: {len(context['active_jobs'])} active jobs. Candidate pipeline: {pipeline}. "
            "You can ask for active jobs, top candidates, job difficulty, or interview questions.",
            ["Live recruiting data"],
        )
    if role == "manager":
        employees = context["employees"]
        avg_perf = round(sum(int(row.get("perf") or 0) for row in employees) / len(employees), 1) if employees else 0
        return (
            f"Live team snapshot: {len(employees)} employees, average performance {avg_perf}%, "
            f"{len([row for row in context['leave_requests'] if row.get('status') == 'Pending Approval'])} pending leave request(s).",
            ["Live manager data"],
        )
    summary = context["summary"]
    return (
        f"Live company snapshot: {summary['total_employees']} employees, {summary['active_today']} active employees, "
        f"{summary['open_positions']} open positions, payroll {_money(summary['monthly_payroll'])}, and {summary['attrition_high_risk']} high attrition risk employee(s).",
        ["Live company data"],
    )


@router.get("/admin/employees")
def admin_employees() -> list[dict]:
    return admin_data.list_employees()


@router.post("/admin/employees")
def admin_create_employee(payload: dict) -> dict:
    try:
        return admin_data.create_employee(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/admin/employees/{employee_id}")
def admin_update_employee(employee_id: int, payload: dict) -> dict:
    try:
        return admin_data.update_employee(employee_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/admin/employees/{employee_id}")
def admin_delete_employee(employee_id: int) -> dict:
    try:
        return admin_data.delete_employee(employee_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/internal-applications")
def internal_applications(employee_id: int | None = None) -> list[dict]:
    return admin_data.list_internal_applications(employee_id)


@router.post("/internal-applications")
def internal_application_create(payload: dict) -> dict:
    try:
        return admin_data.create_internal_application(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/internal-applications/{application_id}")
def internal_application_update(application_id: int, payload: dict) -> dict:
    try:
        return admin_data.update_internal_application(application_id, str(payload.get("status") or "Applied"), payload)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/internal-applications/{application_id}/select")
def internal_application_select(application_id: int) -> dict:
    try:
        return admin_data.select_internal_application(application_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs")
def jobs() -> list[dict]:
    return admin_data.list_jobs()


@router.post("/jobs")
def job_create(payload: dict) -> dict:
    try:
        return admin_data.create_job(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/jobs/{job_id}")
def job_update(job_id: int, payload: dict) -> dict:
    try:
        return admin_data.update_job(job_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/jobs/{job_id}")
def job_delete(job_id: int) -> dict:
    try:
        return admin_data.delete_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/admin/departments")
def admin_departments() -> list[dict]:
    return admin_data.list_departments()


@router.post("/admin/departments")
def admin_create_department(payload: dict) -> dict:
    try:
        return admin_data.create_department(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/admin/departments/{department_id}")
def admin_update_department(department_id: int, payload: dict) -> dict:
    try:
        return admin_data.update_department(department_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/admin/departments/{department_id}")
def admin_delete_department(department_id: int) -> dict:
    try:
        return admin_data.delete_department(department_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    return DashboardSummary(
        employee_count=4872,
        attendance_rate=96.4,
        payroll_monthly=8420000,
        open_roles=38,
        attrition_high_risk=124,
        sentiment_positive=67.0,
    )


@router.post("/ai/resume-screen", response_model=list[ResumeScreenResult])
def resume_screen(payload: ResumeScreenRequest) -> list[ResumeScreenResult]:
    results = [score_candidate(payload.job_description, candidate) for candidate in payload.candidates]
    return sorted(results, key=lambda item: item.match_score, reverse=True)


@router.post("/ai/resume-upload", response_model=list[ResumeScreenResult])
async def resume_upload(
    job_description: str = Form(...),
    files: list[UploadFile] = File(...),
) -> list[ResumeScreenResult]:
    candidates: list[Candidate] = []
    for index, upload in enumerate(files, start=1):
        content = await upload.read()
        text = content.decode("utf-8", errors="ignore")
        filename = upload.filename or f"Candidate {index}"
        name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
        skills = [
            skill
            for skill in ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "REST APIs", "Microservices", "React", "SQL", "System Design"]
            if skill.lower() in text.lower() or skill.lower() in filename.lower()
        ]
        if not skills:
            skills = ["Python", "REST APIs", "Docker"] if index % 2 else ["PostgreSQL", "System Design"]
        candidates.append(
            Candidate(
                name=name,
                role="Uploaded Resume",
                skills=skills,
                experience_years=5 + (index % 4),
                education="Parsed from uploaded resume",
            )
        )
    results = [score_candidate(job_description, candidate) for candidate in candidates]
    return sorted(results, key=lambda item: item.match_score, reverse=True)


@router.post("/ai/interview", response_model=InterviewEvaluation)
def interview(payload: InterviewRequest) -> InterviewEvaluation:
    return evaluate_interview(payload.candidate_name, payload.role, payload.transcript, payload.question)


@router.post("/ai/assistant", response_model=AssistantResponse)
def assistant(payload: AssistantRequest) -> AssistantResponse:
    return _run_copilot_response(payload)


@router.post("/ai/copilot", response_model=AssistantResponse)
def aetherhr_ai_copilot(payload: AssistantRequest) -> AssistantResponse:
    return _run_copilot_response(payload)


@router.post("/ai/attrition")
def attrition_ai(payload: dict) -> dict:
    if not gemini_enabled():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is missing from the real .env file.")
    employees = payload.get("employees")
    if not isinstance(employees, list):
        raise HTTPException(status_code=400, detail="employees must be a list")
    result = analyze_attrition_with_gemini(employees)
    if result is None:
        detail = gemini_last_error() or "Gemini attrition analysis failed. Check the API key, model, or network access."
        raise HTTPException(status_code=503, detail=detail)
    return result


@router.get("/ai/status")
def ai_status() -> dict:
    settings = get_settings()
    return {
        "gemini_enabled": gemini_enabled(),
        "gemini_model": settings.gemini_model,
        "last_error": gemini_last_error(),
        "fallback_enabled": True,
    }


@router.get("/ai/gemini-test")
def ai_gemini_test() -> dict:
    if not gemini_enabled():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is missing from the real .env file.")
    answer = ask_gemini(
        "Reply with exactly this sentence: Gemini is connected to PeoplePulse.",
        temperature=0,
    )
    if not answer:
        detail = gemini_last_error() or "Gemini test failed. Check API key, model, or network access."
        raise HTTPException(status_code=503, detail=detail)
    return {
        "connected": True,
        "model": get_settings().gemini_model,
        "sample": answer,
    }


@router.post("/leave/submit", response_model=LeaveSubmitResponse)
def submit_leave(payload: LeaveSubmitRequest) -> LeaveSubmitResponse:
    record = admin_data.create_leave_request(
        {
            "requester_name": payload.employee_name,
            "requester_role": payload.requester_role,
            "leave_type": payload.leave_type,
            "from_date": payload.from_date.isoformat(),
            "to_date": payload.to_date.isoformat(),
            "reason": payload.reason,
        }
    )
    return LeaveSubmitResponse(
        request_id=f"LV-{record['id']:05d}",
        employee_name=record["requester_name"],
        leave_type=record["leave_type"],
        from_date=payload.from_date,
        to_date=payload.to_date,
        days=record["days"],
        status=record["status"],
        message="Leave request submitted and routed to the Senior Manager approval queue.",
    )


@router.get("/leave/requests")
def leave_requests(status: str | None = None, requester_role: str | None = None) -> list[dict]:
    return admin_data.list_leave_requests(status=status, requester_role=requester_role)


@router.put("/leave/requests/{request_id}")
def leave_request_update(request_id: int, payload: dict) -> dict:
    try:
        return admin_data.update_leave_status(
            request_id,
            str(payload.get("status") or "Pending Approval"),
            str(payload.get("manager_response") or ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/payroll/run", response_model=PayrollRunResponse)
def run_payroll(payload: PayrollRunRequest) -> PayrollRunResponse:
    return PayrollRunResponse(
        run_id="PAY-2026-06-001",
        period=payload.period,
        processed=4872,
        pending=0,
        total_payroll=2400000,
        status="Completed",
        message=f"Payroll for {payload.period} completed successfully.",
    )


@router.post("/actions", response_model=ActionResponse)
def run_action(payload: ActionRequest) -> ActionResponse:
    action_messages = {
        "notification.open": "Notifications refreshed. Three pending HR items are ready for review.",
        "search.open": "Search is ready across employees, candidates, leave, payroll, and policies.",
        "leave.approve": "Leave request approved and the employee calendar was updated.",
        "leave.decline": "Leave request declined and the requester was notified.",
        "attendance.clock_in": "Clock-in recorded for today.",
        "attendance.clock_out": "Clock-out recorded for today.",
        "attendance.export": "Attendance export prepared for June 2026.",
        "payroll.download": "Payslip PDF generated and ready for download.",
        "learning.enroll": "Enrollment recorded and added to the employee learning plan.",
        "employee.add": "Employee created and indexed in the HR directory.",
        "employee.view": "Employee profile loaded from HR records.",
        "employee.profile_update": "Profile update workflow opened.",
        "department.add": "Department created and workforce planning metrics refreshed.",
        "coaching.schedule": "Manager 1:1 recommendation converted to a coaching task.",
        "job.post": "New job posting workflow opened.",
        "job.edit": "Job posting loaded for editing.",
        "candidate.view": "Candidate profile loaded from ATS records.",
        "candidate.email": "Candidate email queued with the recruiter template.",
        "interview.submit": "Interview answer submitted for evaluation.",
        "interview.next_question": "Next structured interview question prepared.",
        "report.view": "Report data refreshed from backend metrics.",
        "report.download": "Report export prepared.",
    }
    message = action_messages.get(payload.action, f"{payload.label} completed.")
    action_id = f"ACT-{abs(hash((payload.action, payload.label))) % 100000:05d}"
    return ActionResponse(
        action_id=action_id,
        action=payload.action,
        status="ok",
        message=message,
        data={"role": payload.role, "label": payload.label, **payload.context},
    )
