# PeoplePulse

PeoplePulse is an AI-powered HRMS and recruitment prototype built for role-based workforce management. It connects Management Admin, Senior Manager, HR Recruiter, and Employee dashboards so employee, attendance, leave, payroll, recruitment, performance, and AI data stay in sync across the app.

## Tech Stack

- Frontend: HTML, CSS, vanilla JavaScript, Chart.js
- Backend: FastAPI, Pydantic Settings
- Database: SQLite for local development, designed to be extendable to PostgreSQL
- AI: Gemini API integration with local fallback logic
- Runtime: Uvicorn

## Main Features

- Role-based login for Management Admin, Senior Manager, HR Recruiter, and Employee.
- Management Admin dashboard with live employee counts, active-today count, open jobs, payroll, department distribution, analytics, performance, and career AI.
- Employee dashboard with personalized profile, attendance clock-in/clock-out, daily work updates, leave, payslips, performance, career growth, career opportunities, applications, HR chatbot, and AI voice interview.
- Senior Manager dashboard with team overview, leave approvals, attendance, performance, and coaching insights.
- HR Recruiter dashboard with job postings, candidates, AI resume screening, candidate pipeline, and AI voice interview reports.
- Internal job applications connecting Employee Career Opportunities with Recruiter Candidates and Management dashboards.
- AI modules for recruitment, resume screening, voice interview evaluation, HR chatbot/copilot, career growth, and AI match score.

## Data Sync

The project is designed so key pages share the same live records:

- Employee Directory drives dashboard employee counts, department distribution, payroll, analytics, performance, and career AI.
- Employee clock-in/clock-out drives active-today status, attendance logs, and performance.
- Employee daily work updates drive performance and career calculations.
- Recruiter Job Postings drive open positions and employee career opportunities.
- Internal Applications drive recruiter candidates, employee application status, interview access, and selection outcomes.
- Completed AI voice interviews notify HR and appear in the HR AI Voice Interview Report tab.

## Environment Setup

Create a `.env` file in the project root:

```env
APP_NAME=PeoplePulse
ENVIRONMENT=development
DATABASE_URL=sqlite:///backend/app/data/aetherhr.sqlite
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_google_ai_studio_key_here
```

The backend reads `.env` from the root folder:

```text
C:\Users\rayin\OneDrive\Documents\umeed\.env
```

Do not commit the real Gemini API key.

## Run Locally

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start the backend:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Docker

```powershell
docker compose up --build
```

## Validate Frontend

```powershell
node scripts\validate-frontend.js
```

## Gemini Notes

Gemini is used for AI-style analysis and natural language generation where available. Database values such as employee count, payroll, attendance, leave balance, job applications, and performance should come from the app data, not from Gemini guesses.

If Gemini is unavailable or the API key is missing, the app uses fallback logic so the demo can still run.

## Project Structure

```text
backend/
  app/
    api/routes.py
    core/config.py
    data/aetherhr.sqlite
    services/admin_data.py
    services/ai.py
frontend/
  index.html
scripts/
  validate-frontend.js
requirements.txt
requirements-ai.txt
docker-compose.yml
Dockerfile
README.md
```

## Hackathon Summary

PeoplePulse shows how an HRMS can combine real-time workforce data with AI-assisted workflows. It supports daily employee operations, manager approvals, recruitment pipelines, internal mobility, AI screening, voice interviews, performance analytics, attrition prediction, and career growth recommendations in one connected system.
