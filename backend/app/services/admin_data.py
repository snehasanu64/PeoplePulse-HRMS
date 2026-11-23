from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "backend" / "app" / "data" / "aetherhr.sqlite"


EMPLOYEE_SEED = [
    ("Sarah Chen", "VP Engineering", "Engineering", "Active", "SC", "#2563EB", "2022-03-15", 180000, 94, "Low"),
    ("Marcus Thompson", "Sr. Designer", "Design", "Active", "MT", "#7C3AED", "2021-08-20", 120000, 88, "Low"),
    ("Priya Sharma", "Product Manager", "Product", "Active", "PS", "#0D9488", "2023-01-10", 145000, 91, "Medium"),
    ("James Wilson", "Backend Engineer", "Engineering", "On Leave", "JW", "#D97706", "2022-11-05", 130000, 78, "High"),
    ("Aisha Patel", "Data Scientist", "Analytics", "Active", "AP", "#DC2626", "2023-06-01", 155000, 96, "Low"),
    ("Leo Nakamura", "DevOps Engineer", "Engineering", "Active", "LN", "#16A34A", "2021-04-18", 140000, 85, "Low"),
    ("Kevin Park", "Sales Director", "Sales", "Active", "KP", "#DB2777", "2020-09-14", 165000, 89, "Low"),
    ("Julia Chen", "Operations Manager", "Operations", "Active", "JC", "#0891B2", "2021-02-22", 138000, 84, "Low"),
    ("Daniel Okafor", "Frontend Engineer", "Engineering", "Active", "DO", "#4F46E5", "2023-03-06", 128000, 86, "Low"),
    ("Emma Rossi", "UX Researcher", "Design", "Active", "ER", "#EA580C", "2024-01-15", 112000, 83, "Medium"),
    ("Ravi Menon", "Account Executive", "Sales", "Active", "RM", "#16A34A", "2023-09-11", 98000, 80, "Medium"),
    ("Chloe Dubois", "HR Business Partner", "Operations", "Active", "CD", "#7C3AED", "2022-07-04", 118000, 90, "Low"),
    ("Tom Becker", "QA Engineer", "Engineering", "On Leave", "TB", "#DC2626", "2024-05-20", 115000, 76, "High"),
    ("Nadia Haddad", "Product Marketing Manager", "Product", "Active", "NH", "#0D9488", "2022-12-01", 122000, 87, "Low"),
]

DEPARTMENT_SEED = [
    ("Engineering", "Sarah Chen", 2400000, 88),
    ("Product", "Priya Sharma", 1450000, 91),
    ("Design", "Marcus Thompson", 900000, 88),
    ("Analytics", "Aisha Patel", 1100000, 96),
    ("Sales", "Kevin Park", 1250000, 82),
    ("Operations", "Julia Chen", 800000, 84),
]

JOB_SEED = [
    ("Senior Backend Engineer", "Engineering", "Active"),
    ("Product Designer", "Design", "Active"),
    ("Data Scientist", "Analytics", "Active"),
    ("Frontend Developer", "Engineering", "Paused"),
    ("DevOps Engineer", "Engineering", "Active"),
    ("Product Manager", "Product", "Active"),
    ("Sales Executive", "Sales", "Active"),
    ("Customer Success Manager", "Sales", "Paused"),
    ("HR Operations Specialist", "Operations", "Active"),
    ("QA Automation Engineer", "Engineering", "Active"),
]


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "AE"


def log_activity(conn: sqlite3.Connection, event_type: str, description: str) -> None:
    conn.execute(
        "INSERT INTO activity_logs(event_type, description, created_at) VALUES (?, ?, ?)",
        (event_type, description, datetime.utcnow().isoformat(timespec="seconds")),
    )


def init_admin_database() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                dept TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active',
                avatar TEXT NOT NULL,
                color TEXT NOT NULL,
                joined TEXT NOT NULL,
                salary REAL NOT NULL DEFAULT 0,
                perf INTEGER NOT NULL DEFAULT 80,
                attrition TEXT NOT NULL DEFAULT 'Low'
            );
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                head TEXT NOT NULL,
                budget REAL NOT NULL DEFAULT 0,
                performance INTEGER NOT NULL DEFAULT 80
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                dept TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active'
            );
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_name TEXT NOT NULL,
                requester_role TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                days INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending Approval',
                manager_response TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS internal_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                job_title TEXT NOT NULL,
                job_dept TEXT NOT NULL,
                job_role TEXT NOT NULL,
                job_salary REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Applied',
                ai_score INTEGER NOT NULL DEFAULT 0,
                interview_score INTEGER NOT NULL DEFAULT 0,
                interview_communication_score INTEGER NOT NULL DEFAULT 0,
                interview_technical_score INTEGER NOT NULL DEFAULT 0,
                interview_confidence_score INTEGER NOT NULL DEFAULT 0,
                interview_summary TEXT NOT NULL DEFAULT '',
                interview_completed_at TEXT,
                applied_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS promotion_transfer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                application_id INTEGER NOT NULL,
                previous_department TEXT NOT NULL,
                new_department TEXT NOT NULL,
                previous_role TEXT NOT NULL,
                new_role TEXT NOT NULL,
                previous_salary REAL NOT NULL DEFAULT 0,
                new_salary REAL NOT NULL DEFAULT 0,
                changed_at TEXT NOT NULL
            );
            """
        )
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(internal_applications)").fetchall()}
        if "interview_score" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_score INTEGER NOT NULL DEFAULT 0")
        if "interview_communication_score" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_communication_score INTEGER NOT NULL DEFAULT 0")
        if "interview_technical_score" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_technical_score INTEGER NOT NULL DEFAULT 0")
        if "interview_confidence_score" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_confidence_score INTEGER NOT NULL DEFAULT 0")
        if "interview_summary" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_summary TEXT NOT NULL DEFAULT ''")
        if "interview_completed_at" not in existing_columns:
            conn.execute("ALTER TABLE internal_applications ADD COLUMN interview_completed_at TEXT")
        if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            conn.executemany(
                """
                INSERT INTO employees(name, role, dept, status, avatar, color, joined, salary, perf, attrition)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                EMPLOYEE_SEED,
            )
            log_activity(conn, "seed", "Initial employee records loaded")
        if conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO departments(name, head, budget, performance) VALUES (?, ?, ?, ?)",
                DEPARTMENT_SEED,
            )
            log_activity(conn, "seed", "Initial department records loaded")
        if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
            conn.executemany("INSERT INTO jobs(title, dept, status) VALUES (?, ?, ?)", JOB_SEED)
            log_activity(conn, "seed", "Initial job records loaded")


def list_internal_applications(employee_id: int | None = None) -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        sql = """
            SELECT ia.*, e.name AS employee_name, e.role AS employee_role, e.dept AS employee_dept,
                   e.salary AS employee_salary, e.perf AS employee_perf
            FROM internal_applications ia
            JOIN employees e ON e.id = ia.employee_id
        """
        params: tuple[Any, ...] = ()
        if employee_id is not None:
            sql += " WHERE ia.employee_id = ?"
            params = (employee_id,)
        sql += " ORDER BY ia.applied_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [row_to_dict(row) for row in rows]


def list_jobs() -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [row_to_dict(row) for row in rows]


def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    title = str(payload.get("title") or payload.get("t") or "").strip()
    dept = str(payload.get("dept") or "Engineering").strip()
    status = str(payload.get("status") or "Active").strip()
    if not title:
        raise ValueError("Job title is required")
    with connect() as conn:
        cursor = conn.execute("INSERT INTO jobs(title, dept, status) VALUES (?, ?, ?)", (title, dept, status))
        log_activity(conn, "job.created", f"{title} job posted")
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def update_job(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    title = str(payload.get("title") or payload.get("t") or "").strip()
    dept = str(payload.get("dept") or "Engineering").strip()
    status = str(payload.get("status") or "Active").strip()
    if not title:
        raise ValueError("Job title is required")
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Job not found")
        conn.execute("UPDATE jobs SET title=?, dept=?, status=? WHERE id=?", (title, dept, status, job_id))
        log_activity(conn, "job.updated", f"{title} job updated")
        updated = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row_to_dict(updated)


def delete_job(job_id: int) -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Job not found")
        job = row_to_dict(row)
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.execute("DELETE FROM internal_applications WHERE job_id=?", (job_id,))
        log_activity(conn, "job.deleted", f"{job['title']} job deleted")
        return job


def create_internal_application(payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    employee_id = int(payload.get("employee_id") or 0)
    job_id = int(payload.get("job_id") or 0)
    now = str(payload.get("applied_at") or datetime.now().astimezone().isoformat(timespec="seconds"))
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM internal_applications WHERE employee_id=? AND job_id=? AND status NOT IN ('Rejected', 'Selected', 'Withdrawn')",
            (employee_id, job_id),
        ).fetchone()
        if existing:
            return row_to_dict(existing)
        cursor = conn.execute(
            """
            INSERT INTO internal_applications(employee_id, job_id, job_title, job_dept, job_role, job_salary, status, ai_score, applied_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Applied', ?, ?, ?)
            """,
            (
                employee_id,
                job_id,
                str(payload.get("job_title") or "Internal Role"),
                str(payload.get("job_dept") or "Unassigned"),
                str(payload.get("job_role") or payload.get("job_title") or "Internal Role"),
                float(payload.get("job_salary") or 0),
                int(payload.get("ai_score") or 0),
                now,
                now,
            ),
        )
        log_activity(conn, "internal_application.created", f"{payload.get('employee_name', 'Employee')} applied for {payload.get('job_title', 'internal role')}")
        row = conn.execute("SELECT * FROM internal_applications WHERE id=?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def update_internal_application(application_id: int, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    init_admin_database()
    payload = payload or {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connect() as conn:
        interview_score = int(payload.get("interview_score") or 0)
        interview_communication_score = int(payload.get("interview_communication_score") or 0)
        interview_technical_score = int(payload.get("interview_technical_score") or 0)
        interview_confidence_score = int(payload.get("interview_confidence_score") or 0)
        interview_summary = str(payload.get("interview_summary") or "")
        interview_completed_at = now if status == "Interview Completed" else payload.get("interview_completed_at")
        if status == "Interview Completed":
            conn.execute(
                """
                UPDATE internal_applications
                SET status=?, interview_score=?, interview_communication_score=?, interview_technical_score=?,
                    interview_confidence_score=?, interview_summary=?, interview_completed_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    status,
                    interview_score,
                    interview_communication_score,
                    interview_technical_score,
                    interview_confidence_score,
                    interview_summary,
                    interview_completed_at,
                    now,
                    application_id,
                ),
            )
        else:
            conn.execute("UPDATE internal_applications SET status=?, updated_at=? WHERE id=?", (status, now, application_id))
        log_activity(conn, "internal_application.updated", f"Internal application #{application_id} moved to {status}")
        row = conn.execute("SELECT * FROM internal_applications WHERE id=?", (application_id,)).fetchone()
        if row is None:
            raise ValueError("Internal application not found")
        return row_to_dict(row)


def select_internal_application(application_id: int) -> dict[str, Any]:
    init_admin_database()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connect() as conn:
        app_row = conn.execute("SELECT * FROM internal_applications WHERE id=?", (application_id,)).fetchone()
        if app_row is None:
            raise ValueError("Internal application not found")
        app = row_to_dict(app_row)
        employee = conn.execute("SELECT * FROM employees WHERE id=?", (app["employee_id"],)).fetchone()
        if employee is None:
            raise ValueError("Employee not found")
        before = row_to_dict(employee)
        new_salary = float(app["job_salary"] or before["salary"])
        if new_salary <= 0:
            new_salary = round(float(before["salary"]) * 1.12)
        conn.execute(
            "UPDATE employees SET dept=?, role=?, salary=? WHERE id=?",
            (app["job_dept"], app["job_role"], new_salary, app["employee_id"]),
        )
        conn.execute("UPDATE internal_applications SET status='Selected', updated_at=? WHERE id=?", (now, application_id))
        conn.execute(
            """
            INSERT INTO promotion_transfer_history(employee_id, application_id, previous_department, new_department, previous_role, new_role, previous_salary, new_salary, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app["employee_id"],
                application_id,
                before["dept"],
                app["job_dept"],
                before["role"],
                app["job_role"],
                float(before["salary"]),
                new_salary,
                now,
            ),
        )
        log_activity(conn, "internal_application.selected", f"{before['name']} selected for {app['job_title']}")
        selected = conn.execute("SELECT * FROM internal_applications WHERE id=?", (application_id,)).fetchone()
        return row_to_dict(selected)


def list_employees() -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()
        return [row_to_dict(row) for row in rows]


def create_employee(payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    name = str(payload.get("name") or "").strip()
    role = str(payload.get("role") or "").strip()
    dept = str(payload.get("dept") or "Engineering").strip()
    status = str(payload.get("status") or "Active").strip()
    joined = str(payload.get("joined") or datetime.utcnow().date().isoformat()).strip()
    salary = float(payload.get("salary") or 0)
    perf = int(payload.get("perf") or 82)
    attrition = str(payload.get("attrition") or "Low").strip()
    color = str(payload.get("color") or "#2563EB")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO employees(name, role, dept, status, avatar, color, joined, salary, perf, attrition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, role, dept, status, initials(name), color, joined, salary, perf, attrition),
        )
        log_activity(conn, "employee.added", f"{name} added to {dept}")
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def update_employee(employee_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    current = get_employee(employee_id)
    updated = {**current, **payload}
    updated["avatar"] = initials(str(updated["name"]))
    with connect() as conn:
        conn.execute(
            """
            UPDATE employees
            SET name=?, role=?, dept=?, status=?, avatar=?, color=?, joined=?, salary=?, perf=?, attrition=?
            WHERE id=?
            """,
            (
                updated["name"],
                updated["role"],
                updated["dept"],
                updated["status"],
                updated["avatar"],
                updated["color"],
                updated["joined"],
                float(updated["salary"]),
                int(updated["perf"]),
                updated["attrition"],
                employee_id,
            ),
        )
        log_activity(conn, "employee.updated", f"{updated['name']} updated")
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        return row_to_dict(row)


def delete_employee(employee_id: int) -> dict[str, Any]:
    init_admin_database()
    employee = get_employee(employee_id)
    with connect() as conn:
        conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        log_activity(conn, "employee.deleted", f"{employee['name']} removed from employee directory")
    return employee


def get_employee(employee_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        if row is None:
            raise ValueError("Employee not found")
        return row_to_dict(row)


def list_departments() -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.*, COUNT(e.id) AS count, COALESCE(ROUND(AVG(e.perf)), d.performance) AS avg_performance
            FROM departments d
            LEFT JOIN employees e ON e.dept = d.name
            GROUP BY d.id
            ORDER BY d.name
            """
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def create_department(payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    name = str(payload.get("name") or "").strip()
    head = str(payload.get("head") or "Unassigned").strip()
    budget = float(payload.get("budget") or 0)
    performance = int(payload.get("performance") or 80)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO departments(name, head, budget, performance) VALUES (?, ?, ?, ?)",
            (name, head, budget, performance),
        )
        log_activity(conn, "department.created", f"{name} department created")
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def update_department(department_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        current = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
        if current is None:
            raise ValueError("Department not found")
        before = row_to_dict(current)
        updated = {**before, **payload}
        conn.execute(
            "UPDATE departments SET name=?, head=?, budget=?, performance=? WHERE id=?",
            (updated["name"], updated["head"], float(updated["budget"]), int(updated["performance"]), department_id),
        )
        if before["name"] != updated["name"]:
            conn.execute("UPDATE employees SET dept=? WHERE dept=?", (updated["name"], before["name"]))
        log_activity(conn, "department.updated", f"{before['name']} department updated")
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
        return row_to_dict(row)


def delete_department(department_id: int) -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
        if row is None:
            raise ValueError("Department not found")
        department = row_to_dict(row)
        conn.execute("DELETE FROM departments WHERE id = ?", (department_id,))
        conn.execute("UPDATE employees SET dept='Unassigned' WHERE dept=?", (department["name"],))
        log_activity(conn, "department.deleted", f"{department['name']} department deleted")
        return department


def dashboard_summary() -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM employees WHERE status = 'Active'").fetchone()[0]
        open_roles = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'Active'").fetchone()[0]
        payroll = conn.execute("SELECT COALESCE(SUM(salary), 0) FROM employees").fetchone()[0]
        high_risk = conn.execute("SELECT COUNT(*) FROM employees WHERE attrition = 'High'").fetchone()[0]
        avg_perf = conn.execute("SELECT COALESCE(ROUND(AVG(perf), 1), 0) FROM employees").fetchone()[0]
        return {
            "total_employees": total,
            "active_today": active,
            "active_rate": round((active / total) * 100, 1) if total else 0,
            "open_positions": open_roles,
            "monthly_payroll": payroll,
            "attrition_high_risk": high_risk,
            "average_performance": avg_perf,
        }


def employee_growth() -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%Y-%m', joined) AS period, COUNT(*) AS hires
            FROM employees
            GROUP BY period
            ORDER BY period
            """
        ).fetchall()
        cumulative = 0
        data = []
        for row in rows:
            cumulative += int(row["hires"])
            data.append({"period": row["period"], "hires": row["hires"], "employees": cumulative})
        return data


def department_distribution() -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        rows = conn.execute(
            """
            SELECT dept AS department, COUNT(*) AS count, COALESCE(ROUND(AVG(perf), 1), 0) AS performance
            FROM employees
            GROUP BY dept
            ORDER BY count DESC
            """
        ).fetchall()
        return [
            {
                "department": row["department"],
                "count": row["count"],
                "percentage": round((row["count"] / total) * 100, 1) if total else 0,
                "performance": row["performance"],
            }
            for row in rows
        ]


def recent_activity(limit: int = 8) -> list[dict[str, Any]]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def payroll_overview() -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        rows = conn.execute(
            "SELECT dept AS department, COALESCE(SUM(salary), 0) AS payroll FROM employees GROUP BY dept ORDER BY payroll DESC"
        ).fetchall()
        total = sum(float(row["payroll"]) for row in rows)
        return {"total": total, "by_department": [row_to_dict(row) for row in rows]}


def workforce_metrics() -> dict[str, Any]:
    init_admin_database()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM employees WHERE status='Active'").fetchone()[0]
        avg_perf = conn.execute("SELECT COALESCE(ROUND(AVG(perf), 1), 0) FROM employees").fetchone()[0]
        risk_rows = conn.execute("SELECT attrition, COUNT(*) AS count FROM employees GROUP BY attrition").fetchall()
        return {
            "total": total,
            "active": active,
            "inactive": max(total - active, 0),
            "average_performance": avg_perf,
            "attrition": [row_to_dict(row) for row in risk_rows],
        }


def leave_days(from_date: str, to_date: str) -> int:
    start = datetime.fromisoformat(from_date).date()
    end = datetime.fromisoformat(to_date).date()
    return max((end - start).days + 1, 1)


def create_leave_request(payload: dict[str, Any]) -> dict[str, Any]:
    init_admin_database()
    requester_name = str(payload.get("requester_name") or "Management Admin")
    requester_role = str(payload.get("requester_role") or "admin")
    leave_type = str(payload.get("leave_type") or "Annual Leave")
    from_date = str(payload.get("from_date"))
    to_date = str(payload.get("to_date"))
    reason = str(payload.get("reason") or "")
    days = leave_days(from_date, to_date)
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO leave_requests(
                requester_name, requester_role, leave_type, from_date, to_date, days,
                reason, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending Approval', ?, ?)
            """,
            (requester_name, requester_role, leave_type, from_date, to_date, days, reason, now, now),
        )
        log_activity(conn, "leave.submitted", f"{requester_name} submitted {leave_type}")
        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def list_leave_requests(status: str | None = None, requester_role: str | None = None) -> list[dict[str, Any]]:
    init_admin_database()
    filters: list[str] = []
    params: list[Any] = []
    if status:
        filters.append("status = ?")
        params.append(status)
    if requester_role:
        filters.append("requester_role = ?")
        params.append(requester_role)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM leave_requests {where} ORDER BY id DESC",
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]


def update_leave_status(request_id: int, status: str, manager_response: str = "") -> dict[str, Any]:
    init_admin_database()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
        if row is None:
            raise ValueError("Leave request not found")
        current = row_to_dict(row)
        conn.execute(
            """
            UPDATE leave_requests
            SET status = ?, manager_response = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, manager_response, now, request_id),
        )
        log_activity(conn, "leave.updated", f"{current['requester_name']} leave {status.lower()}")
        updated = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
        return row_to_dict(updated)
