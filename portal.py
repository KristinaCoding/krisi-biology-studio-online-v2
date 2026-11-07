import os, sqlite3, secrets, hashlib, hmac, json, html
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
from materials_library import register as register_materials
from homework import register as register_homework
from calendar_schedule import register as register_calendar
from student_progress import register as register_progress
from email_notifications import register as register_notifications, notify_student, notify_teacher
from certificates import register as register_certificates
from shared_whiteboard import register as register_whiteboard
from live_classroom import register as register_classroom
from biology_activities import register as register_activities



SECRET=os.environ.get("PORTAL_SECRET","")
if len(SECRET)<32: raise RuntimeError("Set PORTAL_SECRET to a random 32+ character value")
DB=Path(__file__).with_name("portal.db")
from student_activation_api import router as student_activation_router

app=FastAPI()
app.include_router(student_activation_router)
app.include_router(password_recovery_router)
app.add_middleware(SessionMiddleware,secret_key=SECRET,https_only=os.environ.get("PORTAL_HTTPS")=="1",same_site="lax",max_age=3600)
def conn():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c
with conn() as c:
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,display TEXT,role TEXT,passhash TEXT,supabase_user_id TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY,student_id INTEGER,title TEXT,meeting_url TEXT);
    CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY,student_id INTEGER,title TEXT,questions TEXT);
    CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY,quiz_id INTEGER,student_id INTEGER,score INTEGER,total INTEGER,UNIQUE(quiz_id,student_id));
    CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY,student_id INTEGER,requested TEXT,status TEXT DEFAULT 'Requested');
    ''')
    columns = {row[1] for row in c.execute('PRAGMA table_info(users)')}
    if 'supabase_user_id' not in columns:
        c.execute('ALTER TABLE users ADD COLUMN supabase_user_id TEXT')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_supabase_id ON users(supabase_user_id)')
def E(x):return html.escape(str(x or ""),quote=True)
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

register_materials(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_homework(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_calendar(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_progress(app, conn, require=lambda req, role: require(req, role), page=page, E=E)
register_notifications(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_certificates(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_whiteboard(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_classroom(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)
register_activities(app, conn, require=lambda req, role: require(req, role), page=page, token=lambda req: token(req), verifycsrf=lambda req, csrf: verifycsrf(req, csrf), E=E)

def redirect(url):return RedirectResponse(url,status_code=303)

def find_or_create_portal_user(authenticated):
    """Resolve a Supabase-authenticated user to a local portal account."""
    supabase_id = authenticated["supabase_user_id"]
    email = authenticated["email"]
    role = authenticated["role"]
    if not isinstance(supabase_id, str) or not supabase_id.strip():
        raise HTTPException(403, "Invalid account identity")
    if not isinstance(email, str):
        raise HTTPException(403, "Invalid account email")
    email = email.strip().lower()

    if not email or role not in ("teacher", "student"):
        raise HTTPException(403, "Account access denied")

    with conn() as c:
        existing = c.execute(
            "SELECT * FROM users WHERE supabase_user_id=?",
            (supabase_id,),
        ).fetchone()

        if existing:
            if existing["role"] != role:
                raise HTTPException(403, "Account role mismatch")
            return existing["id"]

        # Never automatically claim an older account by matching email.
        email_conflict = c.execute(
            "SELECT id FROM users WHERE email=?",
            (email,),
        ).fetchone()

        if email_conflict:
            raise HTTPException(403, "Account requires migration")

        cursor = c.execute(
            """
            INSERT INTO users
                (email, display, role, passhash, supabase_user_id)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (email, email, role, supabase_id),
        )

        return cursor.lastrowid

def user(req):
    uid=req.session.get("uid")
    if not isinstance(uid,int):return None
    with conn() as c:return c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
def require(req,role):
    u=user(req)
    if not u:raise HTTPException(401,"Sign in required")
    if u["role"]!=role:raise HTTPException(403,"Access denied")
    return u
def token(req):
    if not req.session.get("csrf"):req.session["csrf"]=secrets.token_urlsafe(24)
    return f'<input type="hidden" name="csrf" value="{E(req.session["csrf"])}">'
def verifycsrf(req,csrf):
    if not csrf or not hmac.compare_digest(str(csrf),str(req.session.get("csrf",""))):raise HTTPException(403)
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

    local_user_id = find_or_create_portal_user(authenticated)

    req.session.clear()
    req.session["uid"] = local_user_id

    return redirect("/")

@app.post("/logout")
def logout(req:Request):
    req.session.clear()
    return redirect("/login")
@app.get("/teacher")
def teacher(req:Request):
    require(req,"teacher")
    with conn() as c:
        students=c.execute("SELECT id,display FROM users WHERE role='student'").fetchall()
        results=c.execute("SELECT u.display,q.title,r.score,r.total FROM results r JOIN users u ON u.id=r.student_id JOIN quizzes q ON q.id=r.quiz_id").fetchall()
        bookings=c.execute("SELECT b.id,b.requested,b.status,u.display FROM bookings b JOIN users u ON u.id=b.student_id").fetchall()
    options="".join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
    body=f'''<p>Teacher workspace — separate from your local Streamlit Studio. Data does not synchronize automatically.</p>
    <article><h2>Invite a student</h2><p>Send a secure invitation. Students choose their own passwords.</p><form method="post" action="/student-invite">{token(req)}<label>Student display name<input name="display" maxlength="150" required></label><label>Student email<input name="email" type="email" maxlength="254" required></label><button>Invite Student</button></form></article>
    <article><h2>Assign lesson and meeting link</h2><form method="post" action="/lesson-create">{token(req)}<select name="student_id">{options}</select><label>Title<input name="title" required></label><label>Provider meeting link (HTTPS)<input name="meeting_url" type="url"></label><button>Assign lesson</button></form></article>
    <article><h2>Assign quiz</h2><form method="post" action="/quiz-create">{token(req)}<select name="student_id">{options}</select><label>Title<input name="title" required></label><p><a href="/quiz-builder">Open visual quiz builder</a> (no JSON editing required)</p><label>Questions JSON<textarea name="questions" rows="7">[{{"question":"Which organelle makes most ATP?","options":["Nucleus","Mitochondrion","Ribosome","Golgi"],"correct":1}}]</textarea></label><button>Assign quiz</button></form></article>
    <article><h2>Results</h2><ul>{''.join(f'<li>{E(r["display"])} — {E(r["title"])}: {r["score"]}/{r["total"]}</li>' for r in results)}</ul></article>
    <article><h2>Bookings</h2><ul>{''.join(f'<li>{E(b["display"])}: {E(b["requested"])} — {E(b["status"])} <form method="post" action="/booking/{b["id"]}">{token(req)}<button name="decision" value="Approved">Approve</button> <button name="decision" value="Declined">Decline</button></form></li>' for b in bookings)}</ul></article>
    <form method="post" action="/logout"><button>Sign out</button></form>'''
    body = (
        '<div class="dashboard-layout"><nav class="dashboard-nav" aria-label="Teacher navigation">'
        '<small>TEACHER WORKSPACE</small>'
        '<a href="#section-1">Invite students</a><a href="#section-2">Lessons</a>'
        '<a href="#section-3">Quizzes</a><a href="/quiz-builder">Quiz Builder</a><a href="/materials">Materials Library</a><a href="/homework">Homework</a><a href="/calendar">Calendar</a><a href="/progress">Student Progress</a><a href="/notifications">Email Notifications</a><a href="/certificates">Certificates</a><a href="/whiteboard">Whiteboard</a><a href="/classroom">Live Classroom</a><a href="/activities">Biology Activities</a><a href="#section-4">Results</a>'
        '<a href="#section-5">Bookings</a></nav><div class="dashboard-main">'
        '<p class="dashboard-intro">Your teaching workspace · Manage lessons and learning in one place.</p>'
        '<div class="dashboard-stats">'
        f'<div class="stat-card"><strong>{len(students)}</strong><span>Students</span></div>'
        f'<div class="stat-card"><strong>{len(results)}</strong><span>Quiz results</span></div>'
        f'<div class="stat-card"><strong>{len(bookings)}</strong><span>Bookings</span></div>'
        '</div><div class="dashboard-panels">'
        + body.replace('<article>', '<article>', 1)
        + '</div></div></div>'
    )
    for index in range(1, 6):
        body = body.replace('<article>', f'<article id="section-{index}">', 1)
    return page("Teacher dashboard",body)
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
    require(req, "teacher")
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
    except Exception:
        raise HTTPException(502, "Supabase invitation failed")

    invited_user = getattr(response, "user", None)
    invited_id = getattr(invited_user, "id", None)

    if not invited_id:
        raise HTTPException(502, "Supabase returned no invited user ID")

    try:
        registered = register_invited_student(str(invited_id), display)
        if not registered:
            raise RuntimeError("Student profile already exists; verify the invitation state")
    except Exception:
        raise HTTPException(
            503,
            "Invitation may have been sent, but student profile registration failed. "
            "Check the account before retrying."
        )

    return redirect("/teacher")

@app.post("/lesson-create")
def lesson_create(req:Request,student_id:int=Form(...),title:str=Form(...),meeting_url:str=Form(""),csrf:str=Form(...)):
    require(req,"teacher");verifycsrf(req,csrf)
    if meeting_url and not meeting_url.startswith("https://"):raise HTTPException(400,"HTTPS required")
    with conn() as c:
        if not c.execute("SELECT id FROM users WHERE id=? AND role='student'",(student_id,)).fetchone():raise HTTPException(400)
        c.execute("INSERT INTO lessons(student_id,title,meeting_url) VALUES(?,?,?)",(student_id,title,meeting_url))
    return redirect("/teacher")
@app.get("/quiz-builder")
def quiz_builder(req: Request):
    require(req, "teacher")
    with conn() as c:
        students = c.execute("SELECT id,display FROM users WHERE role='student'").fetchall()
    options = "".join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
    body = (
        '<article><h2>Visual quiz builder</h2>'
        '<p>Create multiple-choice questions without writing JSON. Each question has four answers.</p>'
        f'<form method="post" action="/quiz-builder">{token(req)}'
        f'<label>Student<select name="student_id" required>{options}</select></label>'
        '<label>Quiz title<input name="title" maxlength="200" required></label>'
        '<div id="questions"></div>'
        '<button type="button" id="add-question">Add question</button>'
        '<button type="submit">Save quiz</button></form></article>'
        '<script src="/static/quiz_builder.js" defer></script>'
    )
    return page("Visual quiz builder", body)

@app.post("/quiz-builder")
def quiz_builder_save(req: Request, student_id: int = Form(...), title: str = Form(...),
                      question: list[str] = Form(...), option_a: list[str] = Form(...),
                      option_b: list[str] = Form(...), option_c: list[str] = Form(...),
                      option_d: list[str] = Form(...), correct: list[int] = Form(...),
                      csrf: str = Form(...)):
    require(req, "teacher")
    verifycsrf(req, csrf)
    lengths = [len(v) for v in (question, option_a, option_b, option_c, option_d, correct)]
    if len(set(lengths)) != 1 or not 1 <= lengths[0] <= 30:
        raise HTTPException(400, "Quiz must have 1 to 30 complete questions")
    items = []
    for i in range(lengths[0]):
        opts = [option_a[i].strip(), option_b[i].strip(), option_c[i].strip(), option_d[i].strip()]
        prompt = question[i].strip()
        if not prompt or len(prompt) > 1000 or any(not o or len(o) > 500 for o in opts) or correct[i] not in range(4):
            raise HTTPException(400, "Invalid question or answer")
        items.append({"question": prompt, "options": opts, "correct": correct[i]})
    if not title.strip() or len(title) > 200:
        raise HTTPException(400, "Invalid quiz title")
    with conn() as c:
        if not c.execute("SELECT id FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
            raise HTTPException(400, "Invalid student")
        c.execute("INSERT INTO quizzes(student_id,title,questions) VALUES(?,?,?)",
                  (student_id, title.strip(), json.dumps(items)))
    return redirect("/teacher")

@app.post("/quiz-create")
def quiz_create(req:Request,student_id:int=Form(...),title:str=Form(...),questions:str=Form(...),csrf:str=Form(...)):
    require(req,"teacher");verifycsrf(req,csrf)
    try:
        items=json.loads(questions)
        if not isinstance(items,list) or not 1<=len(items)<=30:raise ValueError()
        for q in items:
            if not isinstance(q["question"],str) or len(q["options"]) not in (2,4) or not all(isinstance(x,str) for x in q["options"]) or type(q["correct"]) is not int or q["correct"] not in range(len(q["options"])):raise ValueError()
    except (ValueError,KeyError,TypeError):raise HTTPException(400,"Invalid question JSON")
    with conn() as c:
        if not c.execute("SELECT id FROM users WHERE id=? AND role='student'",(student_id,)).fetchone():raise HTTPException(400)
        c.execute("INSERT INTO quizzes(student_id,title,questions) VALUES(?,?,?)",(student_id,title,json.dumps(items)))
    return redirect("/teacher")
@app.get("/student")
def student(req:Request):
    u=require(req,"student")
    with conn() as c:
        lessons=c.execute("SELECT * FROM lessons WHERE student_id=?",(u["id"],)).fetchall()
        quizzes=c.execute("SELECT q.id,q.title,r.score,r.total FROM quizzes q LEFT JOIN results r ON r.quiz_id=q.id AND r.student_id=? WHERE q.student_id=?",(u["id"],u["id"])).fetchall()
        bookings=c.execute("SELECT requested,status FROM bookings WHERE student_id=?",(u["id"],)).fetchall()
    lesson_items="".join(f'<li>{E(l["title"])} '+(f'<a href="{E(l["meeting_url"])}" rel="noopener noreferrer" target="_blank">Join external video meeting</a>' if l["meeting_url"] else "")+"</li>" for l in lessons)
    quiz_items="".join(f'<li>{E(q["title"])} — '+(f'{q["score"]}/{q["total"]}' if q["score"] is not None else f'<a href="/quiz/{q["id"]}">Start quiz</a>')+"</li>" for q in quizzes)
    body=f'''<article><h2>My lessons</h2><ul>{lesson_items}</ul></article><article><h2>My quizzes</h2><ul>{quiz_items}</ul></article>
    <article><h2>Request a lesson</h2><form method="post" action="/booking-create">{token(req)}<label>Preferred date and time (UTC)<input type="datetime-local" name="requested" required></label><button>Request booking</button></form>
    <ul>{''.join(f'<li>{E(b["requested"])} — {E(b["status"])}</li>' for b in bookings)}</ul></article><form method="post" action="/logout"><button>Sign out</button></form>'''
    body = (
        '<div class="dashboard-layout"><nav class="dashboard-nav" aria-label="Student navigation">'
        '<small>STUDENT WORKSPACE</small><a href="#section-1">My lessons</a>'
        '<a href="#section-2">My quizzes</a><a href="/my-materials">My Materials</a><a href="/my-homework">My Homework</a><a href="/my-calendar">My Calendar</a><a href="/my-progress">My Progress</a><a href="/my-certificates">My Certificates</a><a href="/my-whiteboard">My Whiteboard</a><a href="/my-classroom">My Classroom</a><a href="/my-activities">My Activities</a><a href="#section-3">Book a lesson</a>'
        '</nav><div class="dashboard-main">'
        '<p class="dashboard-intro">Your learning space · Lessons, quizzes and bookings.</p>'
        '<div class="dashboard-stats">'
        f'<div class="stat-card"><strong>{len(lessons)}</strong><span>Lessons</span></div>'
        f'<div class="stat-card"><strong>{len(quizzes)}</strong><span>Quizzes</span></div>'
        f'<div class="stat-card"><strong>{len(bookings)}</strong><span>Bookings</span></div>'
        '</div><div class="dashboard-panels">' + body + '</div></div></div>'
    )
    for index in range(1, 4):
        body = body.replace('<article>', f'<article id="section-{index}">', 1)
    return page("Student portal",body)
@app.post("/booking-create")
def booking_create(req:Request,requested:str=Form(...),csrf:str=Form(...)):
    u=require(req,"student");verifycsrf(req,csrf)
    try:
        if datetime.fromisoformat(requested)<=datetime.now():raise ValueError()
    except ValueError:raise HTTPException(400,"Select a future time")
    with conn() as c:c.execute("INSERT INTO bookings(student_id,requested) VALUES(?,?)",(u["id"],requested))
    notify_teacher(conn, "New biology lesson booking request", "A student requested a lesson for " + requested + " UTC. Sign in to Biology Studio to review.")
    return redirect("/student")
@app.post("/booking/{bid}")
def booking_decide(req:Request,bid:int,decision:str=Form(...),csrf:str=Form(...)):
    require(req,"teacher");verifycsrf(req,csrf)
    if decision not in ("Approved","Declined"):raise HTTPException(400)
    with conn() as c:c.execute("UPDATE bookings SET status=? WHERE id=?",(decision,bid))
    with conn() as c:
        booking = c.execute("SELECT student_id,requested FROM bookings WHERE id=?", (bid,)).fetchone()
    if booking:
        notify_student(conn, booking["student_id"], "Biology booking " + decision.lower(), "Your booking for " + booking["requested"] + " UTC has been " + decision.lower() + ".")
    return redirect("/teacher")
@app.get("/quiz/{qid}")
def quiz_view(req:Request,qid:int):
    u=require(req,"student")
    with conn() as c:
        q=c.execute("SELECT * FROM quizzes WHERE id=? AND student_id=?",(qid,u["id"])).fetchone()
        existing=c.execute("SELECT id FROM results WHERE quiz_id=? AND student_id=?",(qid,u["id"])).fetchone()
    if not q:raise HTTPException(404)
    if existing:return redirect("/student")
    body=f'<form method="post">{token(req)}'
    for i,item in enumerate(json.loads(q["questions"])):
        body+=f'<article><h3>{i+1}. {E(item["question"])}</h3>'
        for j,opt in enumerate(item["options"]):body+=f'<label><input type="radio" name="q{i}" value="{j}" required> {E(opt)}</label>'
        body+='</article>'
    return page(q["title"],body+"<button>Submit answers</button></form>")
@app.post("/quiz/{qid}")
async def quiz_submit(req:Request,qid:int):
    u=require(req,"student")
    form=await req.form();verifycsrf(req,form.get("csrf"))
    with conn() as c:
        q=c.execute("SELECT * FROM quizzes WHERE id=? AND student_id=?",(qid,u["id"])).fetchone()
        if not q:raise HTTPException(404)
        questions=json.loads(q["questions"])
        try:
            answers=[int(form[f"q{i}"]) for i in range(len(questions))]
            if any(a not in range(len(item["options"])) for a,item in zip(answers,questions)):raise ValueError()
        except (ValueError,KeyError):raise HTTPException(400,"Answer every question")
        score=sum(a==item["correct"] for a,item in zip(answers,questions))
        try:c.execute("INSERT INTO results(quiz_id,student_id,score,total) VALUES(?,?,?,?)",(qid,u["id"],score,len(questions)))
        except sqlite3.IntegrityError:raise HTTPException(409,"Already submitted")
    return page("Quiz submitted",f"<article>Score: {score}/{len(questions)}</article><a href='/student'>Back</a>")


app.mount(
    "/static",
    StaticFiles(
        directory=Path(__file__).resolve().parent / "static"
    ),
    name="static",
)
