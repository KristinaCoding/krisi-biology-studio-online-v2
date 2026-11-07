"""Teacher/student homework routes using PostgreSQL and Supabase UUID identities."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from database import get_connection


def register(app, require, page, token, verifycsrf, E):
    def valid_uuid(value):
        try:
            return str(UUID(str(value)))
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid student")

    def redirect(url):
        return RedirectResponse(url, status_code=303)

    @app.get("/homework")
    def teacher_homework(req: Request):
        teacher = require(req, "teacher")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.display_name
                FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name
            """, (teacher["id"],))
            students = cur.fetchall()
            cur.execute("""
                SELECT h.id,h.title,h.instructions,h.due_at,s.display_name,
                       sub.answer,sub.submitted_at,sub.grade,sub.feedback
                FROM public.homework h
                JOIN public.teacher_students ts ON ts.teacher_id=h.teacher_id
                    AND ts.student_id=h.student_id
                JOIN public.student_profiles s ON s.id=h.student_id
                LEFT JOIN public.homework_submissions sub
                    ON sub.homework_id=h.id AND sub.student_id=h.student_id
                WHERE h.teacher_id=%s ORDER BY h.id DESC
            """, (teacher["id"],))
            rows = cur.fetchall()
        options = "".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        items = ""
        for hid,title,instructions,due,name,answer,submitted,grade,feedback in rows:
            review = ""
            if submitted is not None:
                review = (f'<p><strong>Student answer:</strong> {E(answer)}</p>'
                          f'<p>Submitted: {E(submitted)}</p>'
                          f'<form method="post" action="/homework/{hid}/review">{token(req)}'
                          f'<label>Grade<input name="grade" maxlength="40" value="{E(grade)}"></label>'
                          f'<label>Feedback<textarea name="feedback" maxlength="4000">{E(feedback)}</textarea></label>'
                          '<button>Save feedback</button></form>')
            items += (f'<article><h2>{E(title)}</h2><p>Student: {E(name)} · Due: {E(due)}'
                      f' · {"Submitted" if submitted else "Awaiting submission"}</p>'
                      f'<p>{E(instructions)}</p>{review}</article>')
        body = ('<p><a href="/teacher">← Teacher dashboard</a></p>'
                '<article><h2>Assign homework</h2>'
                f'<form method="post" action="/homework">{token(req)}'
                f'<label>Student<select name="student_id" required>{options}</select></label>'
                '<label>Title<input name="title" maxlength="150" required></label>'
                '<label>Instructions<textarea name="instructions" maxlength="5000" required></textarea></label>'
                '<label>Due date and time (UTC)<input type="datetime-local" name="due_at" required></label>'
                '<button>Assign homework</button></form></article>'
                + (items or '<article><p>No homework assigned yet.</p></article>'))
        return page("Homework & Assignments", body)

    @app.post("/homework")
    def assign_homework(req: Request, student_id: str = Form(...), title: str = Form(...),
                        instructions: str = Form(...), due_at: str = Form(...),
                        csrf: str = Form(...)):
        teacher = require(req, "teacher")
        verifycsrf(req, csrf)
        student_id = valid_uuid(student_id)
        title, instructions = title.strip(), instructions.strip()
        if not 1 <= len(title) <= 150 or not 1 <= len(instructions) <= 5000:
            raise HTTPException(400, "Invalid homework details")
        try:
            deadline = datetime.strptime(due_at, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid due date")
        if deadline <= datetime.now(timezone.utc):
            raise HTTPException(400, "Due date must be in the future")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                INSERT INTO public.homework(teacher_id,student_id,title,instructions,due_at)
                SELECT ts.teacher_id,ts.student_id,%s,%s,%s
                FROM public.teacher_students ts
                WHERE ts.teacher_id=%s AND ts.student_id=%s
                RETURNING id
            """, (title,instructions,deadline,teacher["id"],student_id))
            if cur.fetchone() is None:
                raise HTTPException(403, "Student is not assigned to this teacher")
        return redirect("/homework")

    @app.get("/my-homework")
    def student_homework(req: Request):
        student = require(req, "student")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                SELECT h.id,h.title,h.instructions,h.due_at,
                       sub.answer,sub.submitted_at,sub.grade,sub.feedback
                FROM public.homework h
                JOIN public.teacher_students ts ON ts.teacher_id=h.teacher_id
                    AND ts.student_id=h.student_id
                LEFT JOIN public.homework_submissions sub
                    ON sub.homework_id=h.id AND sub.student_id=h.student_id
                WHERE h.student_id=%s ORDER BY h.id DESC
            """, (student["id"],))
            rows = cur.fetchall()
        items = ""
        for hid,title,instructions,due,answer,submitted,grade,feedback in rows:
            if submitted:
                status = f'<p>Submitted: {E(submitted)}</p>'
                status += (f'<p>Grade: {E(grade)}</p><p>Feedback: {E(feedback)}</p>'
                           if grade or feedback else '<p>Awaiting teacher feedback</p>')
            elif due <= datetime.now(timezone.utc):
                status = '<p>Submission deadline has passed.</p>'
            else:
                status = (f'<form method="post" action="/my-homework/{hid}/submit">{token(req)}'
                          '<label>Your answer<textarea name="answer" maxlength="10000" required></textarea></label>'
                          '<button>Submit homework</button></form>')
            items += f'<article><h2>{E(title)}</h2><p>Due: {E(due)}</p><p>{E(instructions)}</p>{status}</article>'
        return page("My Homework", '<p><a href="/student">← Student dashboard</a></p>'
                    + (items or '<article><p>No homework assigned yet.</p></article>'))

    @app.post("/my-homework/{homework_id}/submit")
    def submit_homework(req: Request, homework_id: int, answer: str = Form(...),
                        csrf: str = Form(...)):
        student = require(req, "student")
        verifycsrf(req, csrf)
        answer = answer.strip()
        if not 1 <= len(answer) <= 10000:
            raise HTTPException(400, "Answer must be between 1 and 10000 characters")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                INSERT INTO public.homework_submissions(homework_id,student_id,answer)
                SELECT h.id,h.student_id,%s FROM public.homework h
                JOIN public.teacher_students ts ON ts.teacher_id=h.teacher_id
                    AND ts.student_id=h.student_id
                WHERE h.id=%s AND h.student_id=%s AND h.due_at > now()
                ON CONFLICT(homework_id) DO NOTHING RETURNING id
            """, (answer,homework_id,student["id"]))
            if cur.fetchone() is None:
                raise HTTPException(409, "Homework unavailable, overdue, or already submitted")
        return redirect("/my-homework")

    @app.post("/homework/{homework_id}/review")
    def review_homework(req: Request, homework_id: int, grade: str = Form(""),
                        feedback: str = Form(""), csrf: str = Form(...)):
        teacher = require(req, "teacher")
        verifycsrf(req, csrf)
        grade, feedback = grade.strip(), feedback.strip()
        if len(grade) > 40 or len(feedback) > 4000:
            raise HTTPException(400, "Feedback too long")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                UPDATE public.homework_submissions sub
                SET grade=%s,feedback=%s,reviewed_at=now()
                FROM public.homework h
                JOIN public.teacher_students ts ON ts.teacher_id=h.teacher_id
                    AND ts.student_id=h.student_id
                WHERE sub.homework_id=h.id AND sub.student_id=h.student_id
                  AND h.id=%s AND h.teacher_id=%s
                RETURNING sub.id
            """, (grade,feedback,homework_id,teacher["id"]))
            if cur.fetchone() is None:
                raise HTTPException(404, "Submission not found")
        return redirect("/homework")
