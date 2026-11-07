"""Teacher-assigned homework with student submissions and feedback."""
from datetime import datetime
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            instructions TEXT NOT NULL,
            due_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS homework_submissions (
            id INTEGER PRIMARY KEY,
            homework_id INTEGER NOT NULL UNIQUE REFERENCES homework(id) ON DELETE CASCADE,
            student_id INTEGER NOT NULL REFERENCES users(id),
            answer TEXT NOT NULL,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            grade TEXT,
            feedback TEXT,
            reviewed_at TEXT
        );
        """)

    def go(url):
        return RedirectResponse(url, status_code=303)

    @app.get("/homework")
    def teacher_homework(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            rows = c.execute("""SELECT h.*, u.display, s.answer, s.submitted_at, s.grade, s.feedback
                FROM homework h JOIN users u ON u.id=h.student_id
                LEFT JOIN homework_submissions s ON s.homework_id=h.id
                ORDER BY h.id DESC""").fetchall()
        options = "".join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        items = ""
        for h in rows:
            status = "Submitted" if h["submitted_at"] else "Awaiting submission"
            review = ""
            if h["submitted_at"]:
                review = (
                    f'<p><strong>Student answer:</strong> {E(h["answer"])}</p>'
                    f'<p>Submitted: {E(h["submitted_at"])} UTC</p>'
                    f'<form method="post" action="/homework/{h["id"]}/review">{token(req)}'
                    f'<label>Grade<input name="grade" maxlength="40" value="{E(h["grade"])}"></label>'
                    f'<label>Feedback<textarea name="feedback" maxlength="4000">{E(h["feedback"])}</textarea></label>'
                    '<button>Save feedback</button></form>'
                )
            items += (f'<article><h2>{E(h["title"])}</h2><p>Student: {E(h["display"])} · Due: {E(h["due_at"])} UTC · {status}</p>'
                      f'<p>{E(h["instructions"])}</p>{review}</article>')
        body = (
            '<p><a href="/teacher">← Teacher dashboard</a></p>'
            '<article><h2>Assign homework</h2>'
            f'<form method="post" action="/homework">{token(req)}'
            f'<label>Student<select name="student_id" required>{options}</select></label>'
            '<label>Title<input name="title" maxlength="150" required></label>'
            '<label>Instructions<textarea name="instructions" maxlength="5000" required></textarea></label>'
            '<label>Due date and time (UTC)<input type="datetime-local" name="due_at" required></label>'
            '<button>Assign homework</button></form></article>'
            + (items or '<article><p>No homework assigned yet.</p></article>')
        )
        return page("Homework & Assignments", body)

    @app.post("/homework")
    def assign_homework(req: Request, student_id: int = Form(...), title: str = Form(...),
                        instructions: str = Form(...), due_at: str = Form(...), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title, instructions = title.strip(), instructions.strip()
        if not title or len(title) > 150 or not instructions or len(instructions) > 5000:
            raise HTTPException(400, "Invalid homework details")
        try:
            deadline = datetime.strptime(due_at, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise HTTPException(400, "Invalid due date")
        if deadline <= datetime.utcnow():
            raise HTTPException(400, "Due date must be in the future")
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
                raise HTTPException(400, "Choose a valid student")
            c.execute("INSERT INTO homework(student_id,title,instructions,due_at) VALUES(?,?,?,?)",
                      (student_id, title, instructions, due_at))
        return go("/homework")

    @app.get("/my-homework")
    def student_homework(req: Request):
        u = require(req, "student")
        with conn() as c:
            rows = c.execute("""SELECT h.*, s.answer, s.submitted_at, s.grade, s.feedback
                FROM homework h LEFT JOIN homework_submissions s ON s.homework_id=h.id
                WHERE h.student_id=? ORDER BY h.id DESC""", (u["id"],)).fetchall()
        items = ""
        for h in rows:
            if h["submitted_at"]:
                status = f'<p>Submitted: {E(h["submitted_at"])} UTC</p>'
                status += f'<p>Grade: {E(h["grade"])}</p><p>Teacher feedback: {E(h["feedback"])}</p>' if h["grade"] or h["feedback"] else '<p>Awaiting teacher feedback</p>'
            else:
                status = (f'<form method="post" action="/my-homework/{h["id"]}/submit">{token(req)}'
                          '<label>Your answer<textarea name="answer" maxlength="10000" required></textarea></label>'
                          '<button>Submit homework</button></form>')
            items += f'<article><h2>{E(h["title"])}</h2><p>Due: {E(h["due_at"])} UTC</p><p>{E(h["instructions"])}</p>{status}</article>'
        return page("My Homework", '<p><a href="/student">← Student dashboard</a></p>'
                    + (items or '<article><p>No homework assigned yet.</p></article>'))

    @app.post("/my-homework/{homework_id}/submit")
    def submit_homework(req: Request, homework_id: int, answer: str = Form(...), csrf: str = Form(...)):
        u = require(req, "student")
        verifycsrf(req, csrf)
        answer = answer.strip()
        if not answer or len(answer) > 10000:
            raise HTTPException(400, "Answer must be between 1 and 10000 characters")
        with conn() as c:
            h = c.execute("SELECT * FROM homework WHERE id=? AND student_id=?", (homework_id, u["id"])).fetchone()
            if not h:
                raise HTTPException(404)
            if datetime.utcnow() > datetime.strptime(h["due_at"], "%Y-%m-%dT%H:%M"):
                raise HTTPException(400, "The submission deadline has passed")
            existing = c.execute("SELECT 1 FROM homework_submissions WHERE homework_id=?", (homework_id,)).fetchone()
            if existing:
                raise HTTPException(409, "Homework already submitted")
            c.execute("INSERT INTO homework_submissions(homework_id,student_id,answer) VALUES(?,?,?)",
                      (homework_id, u["id"], answer))
        return go("/my-homework")

    @app.post("/homework/{homework_id}/review")
    def review_homework(req: Request, homework_id: int, grade: str = Form(""),
                        feedback: str = Form(""), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        grade, feedback = grade.strip(), feedback.strip()
        if len(grade) > 40 or len(feedback) > 4000:
            raise HTTPException(400, "Feedback too long")
        with conn() as c:
            result = c.execute("""UPDATE homework_submissions
                SET grade=?, feedback=?, reviewed_at=CURRENT_TIMESTAMP
                WHERE homework_id=?""", (grade, feedback, homework_id))
            if result.rowcount != 1:
                raise HTTPException(404, "Submission not found")
        return go("/homework")
