"""Read-only progress dashboards built from quiz and homework records."""
from fastapi import Request, HTTPException

def register(app, conn, require, page, E):
    def overview(student_id):
        with conn() as c:
            student = c.execute("SELECT id,display FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
            if not student:
                raise HTTPException(404, "Student not found")
            quizzes = c.execute("""SELECT q.title, r.score, r.total
                FROM quizzes q LEFT JOIN results r
                ON r.quiz_id=q.id AND r.student_id=q.student_id
                WHERE q.student_id=? ORDER BY q.id DESC""", (student_id,)).fetchall()
            homework = c.execute("""SELECT h.title, h.due_at, s.submitted_at, s.grade, s.feedback
                FROM homework h LEFT JOIN homework_submissions s ON s.homework_id=h.id
                WHERE h.student_id=? ORDER BY h.id DESC""", (student_id,)).fetchall()
        completed = [q for q in quizzes if q["score"] is not None and q["total"] is not None]
        points = sum(q["score"] for q in completed)
        possible = sum(q["total"] for q in completed)
        average = f"{points / possible * 100:.1f}%" if possible else "N/A"
        submitted = sum(1 for h in homework if h["submitted_at"])
        graded = sum(1 for h in homework if h["grade"] is not None and h["grade"] != "")
        stats = (
            '<div class="dashboard-stats">'
            f'<div class="stat-card"><strong>{len(completed)}/{len(quizzes)}</strong><span>Quizzes completed</span></div>'
            f'<div class="stat-card"><strong>{average}</strong><span>Quiz points earned</span></div>'
            f'<div class="stat-card"><strong>{submitted}/{len(homework)}</strong><span>Homework submitted</span></div>'
            f'<div class="stat-card"><strong>{graded}</strong><span>Homework graded</span></div>'
            '</div>'
        )
        quiz_rows = ''.join(
            f'<tr><td>{E(q["title"])}</td><td>{E(str(q["score"]) + "/" + str(q["total"])) if q["score"] is not None else "Not completed"}</td></tr>'
            for q in quizzes
        )
        homework_rows = ''.join(
            f'<tr><td>{E(h["title"])}</td><td>{E(h["due_at"])}</td>'
            f'<td>{"Submitted" if h["submitted_at"] else "Not submitted"}</td>'
            f'<td>{E(h["grade"]) if h["grade"] else "Not graded"}</td>'
            f'<td>{E(h["feedback"])}</td></tr>'
            for h in homework
        )
        return (
            f'<h2>{E(student["display"])}</h2>'
            + stats
            + '<article><h2>Quiz results</h2><table><thead><tr><th>Quiz</th><th>Score</th></tr></thead><tbody>'
            + (quiz_rows or '<tr><td colspan="2">No quizzes assigned.</td></tr>')
            + '</tbody></table></article>'
            + '<article><h2>Homework progress</h2><table><thead><tr><th>Homework</th><th>Due (UTC)</th><th>Status</th><th>Grade</th><th>Feedback</th></tr></thead><tbody>'
            + (homework_rows or '<tr><td colspan="5">No homework assigned.</td></tr>')
            + '</tbody></table></article>'
        )

    @app.get("/progress")
    def teacher_progress(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
        links = ''.join(f'<li><a href="/progress/{s["id"]}">{E(s["display"])}</a></li>' for s in students)
        return page("Student Progress", '<p><a href="/teacher">← Teacher dashboard</a></p>'
                    f'<article><h2>Students</h2><ul>{links or "<li>No students yet.</li>"}</ul></article>')

    @app.get("/progress/{student_id}")
    def teacher_student_progress(req: Request, student_id: int):
        require(req, "teacher")
        return page("Student Progress", '<p><a href="/progress">← All students</a></p>' + overview(student_id))

    @app.get("/my-progress")
    def my_progress(req: Request):
        u = require(req, "student")
        return page("My Progress", '<p><a href="/student">← Student dashboard</a></p>' + overview(u["id"]))
