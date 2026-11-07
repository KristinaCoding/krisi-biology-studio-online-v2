"""Private lesson rooms linked to external video calls and shared whiteboards."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS classroom_rooms (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            meeting_url TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    def valid_meeting_url(value):
        if not value or len(value) > 2000 or any(ord(ch) < 32 for ch in value):
            return False
        try:
            parsed = urlsplit(value)
            return (parsed.scheme == "https" and bool(parsed.hostname)
                    and not parsed.username and not parsed.password
                    and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
        except ValueError:
            return False

    @app.get("/classroom")
    def teacher_classrooms(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            rooms = c.execute("""SELECT r.*, u.display FROM classroom_rooms r
                JOIN users u ON u.id=r.student_id ORDER BY r.scheduled_at DESC""").fetchall()
        options = ''.join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        listing = ''.join(
            f'<li><a href="/classroom/{r["id"]}">{E(r["title"])}</a> — '
            f'{E(r["display"])} · {E(r["scheduled_at"])} UTC</li>' for r in rooms
        )
        body = (
            '<p><a href="/teacher">← Teacher dashboard</a></p>'
            '<article><h2>Create a classroom</h2>'
            '<p>Use a trusted HTTPS video meeting link. Video and screen sharing happen on that provider’s website.</p>'
            f'<form method="post" action="/classroom">{token(req)}'
            f'<label>Student<select name="student_id" required>{options}</select></label>'
            '<label>Lesson title<input name="title" maxlength="150" required></label>'
            '<label>Scheduled time (UTC)<input name="scheduled_at" type="datetime-local" required></label>'
            '<label>Video meeting link (HTTPS)<input name="meeting_url" type="url" maxlength="2000" required></label>'
            '<label>Lesson notes<textarea name="notes" maxlength="3000"></textarea></label>'
            '<button type="submit">Create classroom</button></form></article>'
            f'<article><h2>Classrooms</h2><ul>{listing or "<li>No classrooms yet.</li>"}</ul></article>'
        )
        return page("Live Classroom", body)

    @app.post("/classroom")
    def create_classroom(req: Request, student_id: int = Form(...), title: str = Form(...),
                         scheduled_at: str = Form(...), meeting_url: str = Form(...),
                         notes: str = Form(""), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title, notes, meeting_url = title.strip(), notes.strip(), meeting_url.strip()
        if not title or len(title) > 150 or len(notes) > 3000 or not valid_meeting_url(meeting_url):
            raise HTTPException(400, "Invalid classroom details or video link")
        try:
            when = datetime.strptime(scheduled_at, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid scheduled time")
        if when <= datetime.now(timezone.utc):
            raise HTTPException(400, "Choose a future time")
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
                raise HTTPException(400, "Choose a valid student")
            cur = c.execute("""INSERT INTO classroom_rooms(student_id,title,meeting_url,scheduled_at,notes)
                VALUES(?,?,?,?,?)""", (student_id, title, meeting_url, scheduled_at, notes))
            room_id = cur.lastrowid
        return RedirectResponse(f"/classroom/{room_id}", status_code=303)

    @app.get("/my-classroom")
    def student_classrooms(req: Request):
        u = require(req, "student")
        with conn() as c:
            rooms = c.execute("SELECT * FROM classroom_rooms WHERE student_id=? ORDER BY scheduled_at DESC",
                              (u["id"],)).fetchall()
        listing = ''.join(f'<li><a href="/classroom/{r["id"]}">{E(r["title"])}</a>'
                          f' — {E(r["scheduled_at"])} UTC</li>' for r in rooms)
        return page("My Classroom", '<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>My online lessons</h2><ul>{listing or "<li>No classroom sessions yet.</li>"}</ul></article>')

    @app.get("/classroom/{room_id}")
    def classroom_room(req: Request, room_id: int):
        uid = req.session.get("uid")
        if not isinstance(uid, int):
            raise HTTPException(401, "Sign in required")
        with conn() as c:
            viewer = c.execute("SELECT id,role FROM users WHERE id=?", (uid,)).fetchone()
            room = c.execute("""SELECT r.*, u.display FROM classroom_rooms r
                JOIN users u ON u.id=r.student_id WHERE r.id=?""", (room_id,)).fetchone()
        if not viewer:
            raise HTTPException(401, "Sign in required")
        if not room:
            raise HTTPException(404, "Classroom not found")
        if viewer["role"] != "teacher" and not (viewer["role"] == "student" and viewer["id"] == room["student_id"]):
            raise HTTPException(403, "Access denied")
        back = "/classroom" if viewer["role"] == "teacher" else "/my-classroom"
        body = (
            f'<p><a href="{back}">← Classrooms</a></p>'
            f'<article><h2>{E(room["title"])}</h2>'
            f'<p>Student: {E(room["display"])} · Scheduled: {E(room["scheduled_at"])} UTC</p>'
            f'<p>{E(room["notes"])}</p>'
            f'<p><a href="{E(room["meeting_url"])}" target="_blank" rel="noopener noreferrer">'
            'Join video meeting (external provider)</a></p>'
            f'<p><a href="/whiteboard/{room["student_id"]}">Open shared whiteboard</a></p>'
            '<p>The whiteboard is saved between visits. It does not yet sync drawings live across browsers.</p>'
            '</article>'
        )
        return page("Classroom Session", body)
