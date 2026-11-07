import logging
from database import get_connection
from uuid import UUID
from auth_service import get_user_role
import os, secrets, hashlib, hmac, json, html
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from password_recovery import router as password_recovery_router
from auth_service import authenticate_portal_user
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from biology_activities import register as register_biology_activities
from shared_whiteboard import register as register_shared_whiteboard
from homework import register as register_homework
from certificates import register as register_certificates
from student_progress import register as register_student_progress
from calendar_schedule import register as register_calendar
from live_classroom import register as register_live_classroom

SECRET=os.environ.get("PORTAL_SECRET","")
if len(SECRET)<32: raise RuntimeError("Set PORTAL_SECRET to a random 32+ character value")
from student_activation_api import router as student_activation_router

app = FastAPI()

app.include_router(student_activation_router)
app.include_router(password_recovery_router)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET,
    https_only=os.environ.get("PORTAL_HTTPS") == "1",
    same_site="lax",
    max_age=3600
)

def E(x):
    return html.escape(str(x or ""), quote=True)

def hashpw(password):
    salt=secrets.token_bytes(16)
    return salt.hex()+":"+hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600000).hex()
def checkpw(password,stored):
    try:
        salt,digest=stored.split(":")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),600000).hex(),digest)
    except Exception:return False
def page(title,body):
    # Presentation-only redesign. Existing routes, forms, sessions and data logic are unchanged.
    css = Path(__file__).with_name("dark_academia.css").read_text(encoding="utf-8")
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>' + E(title) + ' · KRISI Biology Studio</title>'
        '<style>' + css + '</style><link rel="stylesheet" href="/static/dashboard_v2.css"></head><body>'
        '<div class="studio-shell"><header class="studio-header">'
        '<a class="studio-brand" href="/"><span class="brand-mark">✦</span>'
        '<span><small>KRISI / STUDIO COLLECTION</small><strong>Biology Studio</strong></span></a>'
        '<span class="studio-edition">DARK ACADEMIA · v1.1</span>'
        '</header><main class="studio-main">'
        '<div class="studio-hero"><span class="eyebrow">LEARNING & DISCOVERY</span>'
        '<h1>' + E(title) + '</h1>'
        '<p>A thoughtful space for biology lessons, assessments and learning.</p>'
        '</div><div class="studio-content">' + body + '</div></main>'
        '<footer>KRISI.SITE &nbsp; · &nbsp; LOCAL STUDENT PORTAL PROTOTYPE</footer>'
        '</div></body></html>'
    )

def redirect(url):
    return RedirectResponse(url, status_code=303)


def user(req):
    supabase_id = req.session.get("supabase_user_id")

    if not isinstance(supabase_id, str):
        return None

    try:
        validated_id = str(UUID(supabase_id))
    except ValueError:
        return None

    role = get_user_role(validated_id)

    if role not in ("teacher", "student"):
        return None

    return {
        "id": validated_id,
        "role": role,
    }
def require(req,role):
    u=user(req)
    if not u:raise HTTPException(401,"Sign in required")
    if u["role"]!=role:raise HTTPException(403,"Access denied")
    return u
def token(req):
    if not req.session.get("csrf"):req.session["csrf"]=secrets.token_urlsafe(24)
    return f'<input type="hidden" name="csrf" value="{E(req.session["csrf"])}">'
def verifycsrf(req, csrf):
    expected = str(req.session.get("csrf", ""))

    if not csrf or not expected or not hmac.compare_digest(
        str(csrf), expected
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired CSRF token"
        )
@app.get("/")
def home(req:Request):
    u=user(req)
    return redirect("/teacher" if u and u["role"]=="teacher" else "/student" if u else "/login")
@app.get("/login")
def login(req:Request):
    return page("Sign in",f'<form method="post">{token(req)}<label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required></label><button>Sign in</button></form>')
@app.post("/login")
def login_post(
    req: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf: str = Form(...),
):
    verifycsrf(req, csrf)

    authenticated = authenticate_portal_user(email, password)

    if authenticated is None:
        return page(
            "Sign in",
            "Invalid email or password. "
            "<a href='/login'>Try again</a>",
        )
    from uuid import UUID

    supabase_user_id = str(UUID(authenticated["supabase_user_id"]))

    req.session.clear()
    req.session["supabase_user_id"] = supabase_user_id

    return redirect("/")

@app.post("/logout")
def logout(req:Request):
    req.session.clear()
    return redirect("/login")
@app.get("/teacher")
def teacher(req: Request):
    teacher_user = require(req, "teacher")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sp.id, sp.display_name
                FROM public.student_profiles AS sp
                JOIN public.teacher_students AS ts ON ts.student_id = sp.id
                WHERE ts.teacher_id = %s
                ORDER BY sp.display_name
            """, (teacher_user["id"],))
            students = [
                {"id": str(row[0]), "display": row[1]}
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT l.id, l.title, sp.display_name, l.created_at
                FROM public.lessons AS l
                JOIN public.student_profiles AS sp ON sp.id = l.student_id
                JOIN public.teacher_students AS ts
                  ON ts.student_id = l.student_id
                 AND ts.teacher_id = l.teacher_id
                WHERE l.teacher_id = %s
                ORDER BY l.created_at DESC
            """, (teacher_user["id"],))
            teacher_lessons = [
                {"id": str(row[0]), "title": row[1],
                 "student": row[2], "created": str(row[3])}
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT
                    q.id,
                    q.title,
                    sp.display_name,
                    q.created_at
                FROM public.quizzes AS q
                JOIN public.student_profiles AS sp
                    ON sp.id = q.student_id
                JOIN public.teacher_students AS ts
                    ON ts.student_id = q.student_id
                   AND ts.teacher_id = q.teacher_id
                WHERE q.teacher_id = %s
                ORDER BY q.created_at DESC
            """, (teacher_user["id"],))

            teacher_quizzes = [
                {
                    "id": str(row[0]),
                    "title": row[1],
                    "student": row[2],
                    "created": str(row[3]),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT sp.display_name, q.title, r.score, r.total
                FROM public.quiz_results AS r
                JOIN public.quizzes AS q ON q.id = r.quiz_id
                JOIN public.student_profiles AS sp ON sp.id = r.student_id
                JOIN public.teacher_students AS ts
                  ON ts.student_id = r.student_id
                 AND ts.teacher_id = q.teacher_id
                WHERE q.teacher_id = %s
                ORDER BY r.submitted_at DESC
            """, (teacher_user["id"],))
            results = [
                {"display": row[0], "title": row[1],
                 "score": row[2], "total": row[3]}
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT b.id, b.requested_at, b.status, sp.display_name
                FROM public.bookings AS b
                JOIN public.student_profiles AS sp ON sp.id = b.student_id
                JOIN public.teacher_students AS ts
                  ON ts.student_id = b.student_id
                 AND ts.teacher_id = b.teacher_id
                WHERE b.teacher_id = %s
                ORDER BY b.requested_at DESC
            """, (teacher_user["id"],))
            bookings = [
                {"id": str(row[0]), "requested": str(row[1]),
                 "status": row[2], "display": row[3]}
                for row in cursor.fetchall()
            ]

    options = "".join(
        f'<option value="{E(s["id"])}">{E(s["display"])}</option>'
        for s in students
    )
    lesson_items = "".join(
        f'<li><strong>{E(lesson["title"])}</strong> — {E(lesson["student"])} '
        f'<form method="post" action="/lesson/{E(lesson["id"])}/delete" '
        'onsubmit="return confirm(&quot;Delete this lesson permanently?&quot;);">'
        f'{token(req)}<button type="submit">Delete</button></form></li>'
        for lesson in teacher_lessons
    ) or '<li>No lessons assigned yet.</li>'
    result_items = "".join(
        f'<li>{E(r["display"])} — {E(r["title"])}: {E(r["score"])}/{E(r["total"])}</li>'
        for r in results
    )
    booking_items = "".join(
        f'<li>{E(b["display"])}: {E(b["requested"])} — {E(b["status"])} '
        + (
            f'<form method="post" action="/booking/{E(b["id"])}">'
            f'{token(req)}'
            '<button name="decision" value="Approved">Approve</button> '
            '<button name="decision" value="Declined">Decline</button></form>'
            if b["status"] == "Requested" else ""
        ) + '</li>'
        for b in bookings
    )

    body = f'''<p>Teacher workspace — separate from your local Streamlit Studio. Data does not synchronize automatically.</p>
    <article><h2>Invite a student</h2><p>Send a secure invitation. Students choose their own passwords.</p><form method="post" action="/student-invite">{token(req)}<label>Student display name<input name="display" maxlength="150" required></label><label>Student email<input name="email" type="email" maxlength="254" required></label><button>Invite Student</button></form></article>
    <article><h2>Assign lesson and meeting link</h2><form method="post" action="/lesson-create">{token(req)}<select name="student_id">{options}</select><label>Title<input name="title" required></label><label>Provider meeting link (HTTPS)<input name="meeting_url" type="url"></label><button>Assign lesson</button></form></article>
    <article><h2>Existing Lessons</h2><ul>{lesson_items}</ul></article>
    <article><h2>Assign quiz</h2><form method="post" action="/quiz-create">{token(req)}<select name="student_id">{options}</select><label>Title<input name="title" required></label><label>Questions JSON<textarea name="questions" rows="7">[{{"question":"Which organelle makes most ATP?","options":["Nucleus","Mitochondrion","Ribosome","Golgi"],"correct":1}}]</textarea></label><button>Assign quiz</button></form></article>    <article>
      <article>
    <h2>Existing Quizzes</h2>
    <ul>
        {''.join(
            f'<li>'
            f'<strong>{E(q["title"])}</strong> — {E(q["student"])} '
            f'<form method="post" action="/quiz/{E(q["id"])}/delete" '
            f'onsubmit="return confirm(&quot;Delete this quiz permanently?&quot;);">'
            f'{token(req)}'
            f'<button type="submit">Delete Quiz</button>'
            f'</form>'
            f'</li>'
            for q in teacher_quizzes
        ) or '<li>No quizzes assigned yet.</li>'}
    </ul>
</article>
    <article><h2>Results</h2><ul>{result_items}</ul></article>
    <article><h2>Bookings</h2><ul>{booking_items}</ul></article>
    <form method="post" action="/logout"><button>Sign out</button></form>'''
    body = (
        '<div class="dashboard-layout"><nav class="dashboard-nav" aria-label="Teacher navigation">'
        '<small>TEACHER WORKSPACE</small>'
        '<a href="#section-1">Invite students</a><a href="#section-2">Lessons</a>'
        '<a href="#section-3">Existing lessons</a><a href="#section-4">Quizzes</a>'
        '<a href="#section-5">Results</a><a href="#section-6">Bookings</a>'
        '</nav><div class="dashboard-main">'
        '<p class="dashboard-intro">Your teaching workspace · Manage lessons and learning in one place.</p>'
        '<div class="dashboard-stats">'
        f'<div class="stat-card"><strong>{len(students)}</strong><span>Students</span></div>'
        f'<div class="stat-card"><strong>{len(results)}</strong><span>Quiz results</span></div>'
        f'<div class="stat-card"><strong>{len(bookings)}</strong><span>Bookings</span></div>'
        '</div><div class="dashboard-panels">' + body + '</div></div></div>'
    )
    for index in range(1, 7):
        body = body.replace('<article>', f'<article id="section-{index}">', 1)
    if os.environ.get("BIOLOGY_V3_ENABLED") == "1":
        body += ('<article><h2>Teaching tools · v3</h2><nav>'
                 '<a href="/homework">Homework</a> · '
                 '<a href="/certificates">Certificates</a> · '
                 '<a href="/progress">Student progress</a> · '
                 '<a href="/calendar">Teaching calendar</a> · '
                 '<a href="/classroom">Live classroom</a> · '
                 '<a href="/activities">Biology activities</a>'
                 '</nav></article>')
    return page("Teacher dashboard", body)
@app.post("/student-create")
def student_create(req:Request,display:str=Form(...),email:str=Form(...),password:str=Form(...),csrf:str=Form(...)):
    require(req,"teacher");verifycsrf(req,csrf)
    raise HTTPException(
        503,
        "Student creation is temporarily disabled. Supabase invitations are being configured."
    )

@app.get("/accept-invite")

def accept_invite_page():
    template_path = Path(__file__).with_name(
        "templates"
    ) / "student_activation.html"

    response = HTMLResponse(
        template_path.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "connect-src 'self' https://ydrexfodapmjamvhnsee.supabase.co; "
                "form-action 'self'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'"
            ),
        },
    )

    return response


@app.post("/accept-invite")
def complete_invitation(req: Request):
    raise HTTPException(
        status_code=503,
        detail="Student activation is being upgraded.",
    )

@app.post("/student-invite")
def student_invite(
    req: Request,
    display: str = Form(...),
    email: str = Form(...),
    csrf: str = Form(...)
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)

    from auth_service import (
        invite_student_by_email,
        register_invited_student,
    )

    display = display.strip()
    email = email.strip().lower()

    if not display or len(display) > 150:
        raise HTTPException(400, "Invalid student display name")

    if not email or len(email) > 254 or "@" not in email:
        raise HTTPException(400, "Invalid student email")

    redirect_url = os.environ.get("STUDENT_INVITE_REDIRECT_URL", "")

    if not redirect_url:
        raise HTTPException(503, "Student invitation redirect is not configured")

    try:
        response = invite_student_by_email(email, redirect_url)
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").exception(
            "Supabase student invitation failed"
        )
        raise HTTPException(
            status_code=502,
            detail="Supabase invitation failed",
        ) from exc

    invited_user = getattr(response, "user", None)
    invited_id = getattr(invited_user, "id", None)

    if not invited_id:
        raise HTTPException(
            status_code=502,
            detail="Supabase invitation returned no user ID"
        )

    try:
        register_invited_student(str(invited_id), display)
    except Exception:
        raise HTTPException(
            503,
            "Invitation may have been sent, but student profile registration failed. "
            "Check the account before retrying."
        )

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO public.teacher_students (
                        teacher_id,
                        student_id
                    )
                    VALUES (%s, %s)
                    ON CONFLICT (teacher_id, student_id)
                    DO NOTHING
                """, (
                    teacher_user["id"],
                    str(UUID(str(invited_id))),
                ))

    except Exception:
        raise HTTPException(
            503,
            "Invitation may have been sent, but teacher-student "
            "linking failed. Check the account before retrying."
        )

    return redirect("/teacher")

@app.post("/lesson/{lesson_id}/delete")
def delete_lesson(
    req: Request,
    lesson_id: str,
    csrf: str = Form(...),
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)
    
    try:
        lesson_uuid = str(UUID(lesson_id))
    except ValueError:
        raise HTTPException(400, "Invalid lesson ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM public.lessons
                WHERE id = %s
                  AND teacher_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM public.teacher_students AS ts
                      WHERE ts.teacher_id = public.lessons.teacher_id
                        AND ts.student_id = public.lessons.student_id
                  )
                RETURNING id
            """, (
                lesson_uuid,
                teacher_user["id"],
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    404,
                    "Lesson not found or access denied"
                )

    return redirect("/teacher")
@app.post("/lesson-create")
def lesson_create(
    req: Request,
    student_id: str = Form(...),
    title: str = Form(...),
    meeting_url: str = Form(""),
    csrf: str = Form(...),
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)

    try:
        student_uuid = str(UUID(student_id))
    except ValueError:
        raise HTTPException(400, "Invalid student ID")

    title = title.strip()
    meeting_url = meeting_url.strip()

    if not title:
        raise HTTPException(400, "Lesson title is required")

    if meeting_url and not meeting_url.startswith("https://"):
        raise HTTPException(400, "HTTPS required")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.lessons (
                    teacher_id,
                    student_id,
                    title,
                    meeting_url
                )
                SELECT %s, ts.student_id, %s, %s
                FROM public.teacher_students AS ts
                WHERE ts.teacher_id = %s
                  AND ts.student_id = %s
                RETURNING id
            """, (
                teacher_user["id"],
                title,
                meeting_url,
                teacher_user["id"],
                student_uuid,
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    403,
                    "Student is not assigned to this teacher"
                )

    return redirect("/teacher")
@app.post("/quiz/{quiz_id}/delete")
def delete_quiz(
    req: Request,
    quiz_id: str,
    csrf: str = Form(...),
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)

    try:
        quiz_uuid = str(UUID(quiz_id))
    except ValueError:
        raise HTTPException(400, "Invalid quiz ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM public.quizzes AS q
                WHERE q.id = %s
                  AND q.teacher_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM public.teacher_students AS ts
                      WHERE ts.teacher_id = q.teacher_id
                        AND ts.student_id = q.student_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.quiz_results AS r
                      WHERE r.quiz_id = q.id
                  )
                RETURNING q.id
            """, (
                quiz_uuid,
                teacher_user["id"],
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    409,
                    "Quiz cannot be deleted. It may have results or be unavailable."
                )

    return redirect("/teacher")
@app.post("/quiz-create")
def quiz_create(
    req: Request,
    student_id: str = Form(...),
    title: str = Form(...),
    questions: str = Form(...),
    csrf: str = Form(...),
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)

    try:
        student_uuid = str(UUID(student_id))
    except ValueError:
        raise HTTPException(400, "Invalid student ID")

    title = title.strip()
    if not title:
        raise HTTPException(400, "Quiz title is required")

    try:
        items = json.loads(questions)

        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            raise ValueError()

        for q in items:
            if not isinstance(q, dict):
                raise ValueError()

            if (
                not isinstance(q["question"], str)
                or not isinstance(q["options"], list)
                or len(q["options"]) not in (2, 4)
                or not all(isinstance(x, str) for x in q["options"])
                or type(q["correct"]) is not int
                or q["correct"] not in range(len(q["options"]))
            ):
                raise ValueError()

    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid question JSON")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.quizzes (
                    teacher_id,
                    student_id,
                    title,
                    questions
                )
                SELECT %s, ts.student_id, %s, %s::jsonb
                FROM public.teacher_students AS ts
                WHERE ts.teacher_id = %s
                  AND ts.student_id = %s
                RETURNING id
            """, (
                teacher_user["id"],
                title,
                json.dumps(items),
                teacher_user["id"],
                student_uuid,
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    403,
                    "Student is not assigned to this teacher"
                )

    return redirect("/teacher")
@app.get("/student")
def student(req: Request):
    student_user = require(req, "student")
    student_id = student_user["id"]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            # Teachers assigned to this student
            cursor.execute("""
                SELECT tp.id, tp.display_name
                FROM public.teacher_profiles AS tp
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = tp.id
                WHERE ts.student_id = %s
                ORDER BY tp.display_name
            """, (student_id,))

            assigned_teachers = [
                {
                    "id": str(row[0]),
                    "display": row[1],
                }
                for row in cursor.fetchall()
            ]
            # Lessons assigned to this student
            cursor.execute("""
                SELECT l.title, l.meeting_url
                FROM public.lessons AS l
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = l.teacher_id
                   AND ts.student_id = l.student_id
                WHERE l.student_id = %s
                ORDER BY l.created_at DESC
            """, (student_id,))

            lessons = [
                {
                    "title": row[0],
                    "meeting_url": row[1],
                }
                for row in cursor.fetchall()
            ]

            # Quizzes and submitted results
            cursor.execute("""
                SELECT q.id, q.title, r.score, r.total
                FROM public.quizzes AS q
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = q.teacher_id
                   AND ts.student_id = q.student_id
                LEFT JOIN public.quiz_results AS r
                    ON r.quiz_id = q.id
                   AND r.student_id = q.student_id
                WHERE q.student_id = %s
                ORDER BY q.created_at DESC
            """, (student_id,))

            quizzes = [
                {
                    "id": str(row[0]),
                    "title": row[1],
                    "score": row[2],
                    "total": row[3],
                }
                for row in cursor.fetchall()
            ]

            # Student bookings
            cursor.execute("""
                SELECT b.requested_at, b.status
                FROM public.bookings AS b
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = b.teacher_id
                   AND ts.student_id = b.student_id
                WHERE b.student_id = %s
                ORDER BY b.requested_at DESC
            """, (student_id,))

            bookings = [
                {
                    "requested": str(row[0]),
                    "status": row[1],
                }
                for row in cursor.fetchall()
            ]

    teacher_options = "".join(
        f'<option value="{E(t["id"])}">{E(t["display"])}</option>'
        for t in assigned_teachers
    )

    if len(assigned_teachers) == 0:
        teacher_field = (
            '<p>No teacher assigned yet. '
            'Booking will be available once a teacher is assigned.</p>'
        )
        booking_disabled = "disabled"

    elif len(assigned_teachers) == 1:
        teacher_field = (
            f'<input type="hidden" name="teacher_id" '
            f'value="{E(assigned_teachers[0]["id"])}">'
            f'<p>Teacher: {E(assigned_teachers[0]["display"])}</p>'
        )
        booking_disabled = ""

    else:
        teacher_field = (
            '<label>Choose your teacher'
            '<select name="teacher_id" required>'
            '<option value="">Select a teacher</option>'
            f'{teacher_options}'
            '</select></label>'
        )
        booking_disabled = ""

    lesson_items = "".join(
        f'<li>{E(l["title"])} '
        + (
            f'<a href="{E(l["meeting_url"])}" '
            'rel="noopener noreferrer" target="_blank">'
            'Join external video meeting</a>'
            if l["meeting_url"] else ""
        )
        + "</li>"
        for l in lessons
    )

    quiz_items = "".join(
        f'<li>{E(q["title"])} — '
        + (
            f'{q["score"]}/{q["total"]}'
            if q["score"] is not None
            else f'<a href="/quiz/{q["id"]}">Start quiz</a>'
        )
        + "</li>"
        for q in quizzes
    )

    booking_items = "".join(
        f'<li>{E(b["requested"])} — {E(b["status"])}</li>'
        for b in bookings
    )

    body = f'''
    <article>
        <h2>My lessons</h2>
        <ul>{lesson_items}</ul>
    </article>

    <article>
        <h2>My quizzes</h2>
        <ul>{quiz_items}</ul>
    </article>

    <article>
        <h2>Request a lesson</h2>

        <form method="post" action="/booking-create">
            {token(req)}
            {teacher_field}

            <label>
                Preferred date and time (UTC)
                <input type="datetime-local"
                       name="requested"
                       required>
            </label>

            <button {booking_disabled}>Request booking</button>
        </form>

        <ul>{booking_items}</ul>
    </article>

    <form method="post" action="/logout">
        <button>Sign out</button>
    </form>
    '''

    body = (
        '<div class="dashboard-layout">'
        '<nav class="dashboard-nav" aria-label="Student navigation">'
        '<small>STUDENT WORKSPACE</small>'
        '<a href="#section-1">My lessons</a>'
        '<a href="#section-2">My quizzes</a>'
        '<a href="#section-3">Book a lesson</a>'
        '</nav>'
        '<div class="dashboard-main">'
        '<p class="dashboard-intro">'
        'Your learning space · Lessons, quizzes and bookings.'
        '</p>'
        '<div class="dashboard-stats">'
        f'<div class="stat-card"><strong>{len(lessons)}</strong>'
        '<span>Lessons</span></div>'
        f'<div class="stat-card"><strong>{len(quizzes)}</strong>'
        '<span>Quizzes</span></div>'
        f'<div class="stat-card"><strong>{len(bookings)}</strong>'
        '<span>Bookings</span></div>'
        '</div>'
        '<div class="dashboard-panels">'
        + body +
        '</div></div></div>'
    )

    for index in range(1, 4):
        body = body.replace(
            '<article>',
            f'<article id="section-{index}">',
            1
        )

    if os.environ.get("BIOLOGY_V3_ENABLED") == "1":
        body += ('<article><h2>Learning tools · v3</h2><nav>'
                 '<a href="/my-homework">My homework</a> · '
                 '<a href="/my-certificates">My certificates</a> · '
                 '<a href="/my-progress">My progress</a> · '
                 '<a href="/my-calendar">My calendar</a> · '
                 '<a href="/my-classroom">My classroom</a> · '
                 '<a href="/my-activities">Biology activities</a>'
                 '</nav></article>')
    return page("Student portal", body)
@app.post("/booking-create")
def booking_create(
    req: Request,
    requested: str = Form(...),
    teacher_id: str = Form(...),
    csrf: str = Form(...),
):
    student_user = require(req, "student")
    verifycsrf(req, csrf)

    try:
        teacher_uuid = str(UUID(teacher_id))
    except ValueError:
        raise HTTPException(400, "Invalid teacher ID")

    try:
        requested_time = datetime.fromisoformat(requested)

        # The booking form explicitly uses UTC.
        if requested_time.tzinfo is None:
            requested_time = requested_time.replace(
                tzinfo=timezone.utc
            )
        else:
            requested_time = requested_time.astimezone(
                timezone.utc
            )

        if requested_time <= datetime.now(timezone.utc):
            raise ValueError()

    except ValueError:
        raise HTTPException(400, "Select a future time")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.bookings (
                    student_id,
                    teacher_id,
                    requested_at,
                    status
                )
                SELECT ts.student_id, ts.teacher_id, %s, %s
                FROM public.teacher_students AS ts
                WHERE ts.student_id = %s
                  AND ts.teacher_id = %s
                RETURNING id
            """, (
                requested_time,
                "Requested",
                student_user["id"],
                teacher_uuid,
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    403,
                    "Teacher is not assigned to this student"
                )

    return redirect("/student")
@app.post("/booking/{bid}")
def booking_decide(
    req: Request,
    bid: str,
    decision: str = Form(...),
    csrf: str = Form(...),
):
    teacher_user = require(req, "teacher")
    verifycsrf(req, csrf)

    if decision not in ("Approved", "Declined"):
        raise HTTPException(400, "Invalid booking decision")

    try:
        booking_uuid = str(UUID(bid))
    except ValueError:
        raise HTTPException(400, "Invalid booking ID")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE public.bookings AS b
                SET status = %s
                WHERE b.id = %s
                  AND b.teacher_id = %s
                  AND b.status = 'Requested'
                  AND EXISTS (
                      SELECT 1
                      FROM public.teacher_students AS ts
                      WHERE ts.teacher_id = b.teacher_id
                        AND ts.student_id = b.student_id
                  )
                RETURNING b.id
            """, (
                decision,
                booking_uuid,
                teacher_user["id"],
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    404,
                    "Booking not found or cannot be updated"
                )

    return redirect("/teacher")
@app.get("/quiz/{qid}")
def quiz_view(req: Request, qid: str):
    student_user = require(req, "student")

    try:
        quiz_uuid = str(UUID(qid))
    except ValueError:
        raise HTTPException(404, "Quiz not found")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT q.title, q.questions
                FROM public.quizzes AS q
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = q.teacher_id
                   AND ts.student_id = q.student_id
                WHERE q.id = %s
                  AND q.student_id = %s
            """, (
                quiz_uuid,
                student_user["id"],
            ))

            quiz_row = cursor.fetchone()

            if quiz_row is None:
                raise HTTPException(404, "Quiz not found")

            cursor.execute("""
                SELECT 1
                FROM public.quiz_results
                WHERE quiz_id = %s
                  AND student_id = %s
                LIMIT 1
            """, (
                quiz_uuid,
                student_user["id"],
            ))

            already_submitted = cursor.fetchone() is not None

    if already_submitted:
        return redirect("/student")

    title, questions = quiz_row

    # PostgreSQL JSONB is normally returned as Python objects.
    if isinstance(questions, str):
        questions = json.loads(questions)

    body = f'<form method="post">{token(req)}'

    for i, item in enumerate(questions):
        body += (
            f'<article><h3>{i + 1}. '
            f'{E(item["question"])}</h3>'
        )

        for j, option in enumerate(item["options"]):
            body += (
                f'<label>'
                f'<input type="radio" name="q{i}" '
                f'value="{j}" required> '
                f'{E(option)}'
                f'</label>'
            )

        body += '</article>'

    body += '<button>Submit answers</button></form>'

    return page(title, body)
@app.post("/quiz/{qid}")
async def quiz_submit(req: Request, qid: str):
    student_user = require(req, "student")

    form = await req.form()
    verifycsrf(req, form.get("csrf"))

    try:
        quiz_uuid = str(UUID(qid))
    except ValueError:
        raise HTTPException(404, "Quiz not found")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT q.questions
                FROM public.quizzes AS q
                JOIN public.teacher_students AS ts
                    ON ts.teacher_id = q.teacher_id
                   AND ts.student_id = q.student_id
                WHERE q.id = %s
                  AND q.student_id = %s
            """, (
                quiz_uuid,
                student_user["id"],
            ))

            row = cursor.fetchone()

            if row is None:
                raise HTTPException(404, "Quiz not found")

            questions = row[0]

            if isinstance(questions, str):
                questions = json.loads(questions)

            try:
                answers = [
                    int(form[f"q{i}"])
                    for i in range(len(questions))
                ]

                if any(
                    answer not in range(len(item["options"]))
                    for answer, item in zip(answers, questions)
                ):
                    raise ValueError()

            except (ValueError, KeyError, TypeError):
                raise HTTPException(
                    400,
                    "Answer every question"
                )

            score = sum(
                answer == item["correct"]
                for answer, item in zip(answers, questions)
            )

            cursor.execute("""
                INSERT INTO public.quiz_results (
                    quiz_id,
                    student_id,
                    score,
                    total
                )
                SELECT q.id, q.student_id, %s, %s
                FROM public.quizzes AS q
                WHERE q.id = %s
                  AND q.student_id = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.quiz_results AS r
                      WHERE r.quiz_id = q.id
                        AND r.student_id = q.student_id
                  )
                RETURNING id
            """, (
                score,
                len(questions),
                quiz_uuid,
                student_user["id"],
            ))

            if cursor.fetchone() is None:
                raise HTTPException(
                    409,
                    "Quiz already submitted"
                )

    return page(
        "Quiz submitted",
        f"<article>Score: {score}/{len(questions)}</article>"
        "<a href='/student'>Back</a>"
    )

# v3 modules are gated until database migrations and staging checks pass.
# The existing PostgreSQL portal stays usable without the new tables.
if os.environ.get("BIOLOGY_V3_ENABLED") == "1":
    register_homework(app, require, page, token, verifycsrf, E)
    register_certificates(app, require, page, token, verifycsrf, E)
    register_student_progress(app, require, page, E)
    register_calendar(app, require, page, token, verifycsrf, E)
    register_live_classroom(app, require, page, token, verifycsrf, E)

register_biology_activities(app, require, page, token, verifycsrf, E)
register_shared_whiteboard(app, None, require, page, token, verifycsrf, E)

app.mount(
    "/static",
    StaticFiles(
        directory=Path(__file__).resolve().parent / "static"
    ),
    name="static",
)