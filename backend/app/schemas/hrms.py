from datetime import date

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    name: str
    role: str
    skills: list[str] = Field(default_factory=list)
    experience_years: int = 0
    education: str = "Not provided"


class ResumeScreenRequest(BaseModel):
    job_description: str
    candidates: list[Candidate]


class ResumeScreenResult(BaseModel):
    candidate: str
    match_score: int
    skills_matched: list[str]
    missing_skills: list[str]
    experience_analysis: str
    education_analysis: str
    recommendation: str


class InterviewRequest(BaseModel):
    candidate_name: str
    role: str
    transcript: str
    question: str = ""


class InterviewEvaluation(BaseModel):
    candidate_name: str
    technical_score: int
    communication_score: int
    confidence_score: int
    transcript_summary: str
    recommendation: str


class AssistantRequest(BaseModel):
    role: str = "employee"
    message: str
    context: dict = Field(default_factory=dict)


class AssistantResponse(BaseModel):
    answer: str
    actions: list[str] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    employee_count: int
    attendance_rate: float
    payroll_monthly: float
    open_roles: int
    attrition_high_risk: int
    sentiment_positive: float


class LeaveSubmitRequest(BaseModel):
    employee_name: str = "Sarah Chen"
    requester_role: str = "admin"
    leave_type: str
    from_date: date
    to_date: date
    reason: str = ""


class LeaveSubmitResponse(BaseModel):
    request_id: str
    employee_name: str
    leave_type: str
    from_date: date
    to_date: date
    days: int
    status: str
    message: str


class PayrollRunRequest(BaseModel):
    period: str = "June 2026"
    initiated_by: str = "Management Admin"


class PayrollRunResponse(BaseModel):
    run_id: str
    period: str
    processed: int
    pending: int
    total_payroll: float
    status: str
    message: str


class ActionRequest(BaseModel):
    action: str
    role: str = "admin"
    label: str
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    action_id: str
    action: str
    status: str
    message: str
    data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
