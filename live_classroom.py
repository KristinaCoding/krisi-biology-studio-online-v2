"""PostgreSQL lesson rooms with external HTTPS video meeting links."""
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID
import ipaddress
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from database import get_connection


def valid_meeting_url(value):
    if not value or len(value)>2000 or any(ord(c)<32 for c in value):
        return False
    try:
        p=urlsplit(value)
        if p.scheme!="https" or not p.hostname or p.username or p.password:
            return False
        host=p.hostname.lower()
        if host=="localhost" or host.endswith(".localhost") or host.endswith(".local"):
            return False
        try:
            ip=ipaddress.ip_address(host)
            if not ip.is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def register(app, require, page, token, verifycsrf, E):
    def viewer(req):
        from auth_service import get_user_role
        try:
            uid=str(UUID(str(req.session.get("supabase_user_id"))))
        except (TypeError,ValueError):
            raise HTTPException(401,"Sign in required")
        role=get_user_role(uid)
        if role not in ("teacher","student"):
            raise HTTPException(403,"Access denied")
        return require(req,role)

    @app.get("/classroom")
    def teacher_classrooms(req: Request):
        teacher=require(req,"teacher")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""",(teacher["id"],))
            students=cur.fetchall()
            cur.execute("""SELECT r.id,r.title,s.display_name,r.scheduled_at
                FROM public.classroom_rooms r
                JOIN public.teacher_students ts ON ts.teacher_id=r.teacher_id AND ts.student_id=r.student_id
                JOIN public.student_profiles s ON s.id=r.student_id
                WHERE r.teacher_id=%s ORDER BY r.scheduled_at DESC""",(teacher["id"],))
            rooms=cur.fetchall()
        options="".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        listing="".join(f'<li><a href="/classroom/{rid}">{E(title)}</a> — {E(name)} · {E(when)} UTC</li>'
                        for rid,title,name,when in rooms)
        body=('<p><a href="/teacher">← Teacher dashboard</a></p>'
              '<article><h2>Create a classroom</h2>'
              '<p>Video and screen sharing use an external HTTPS meeting provider.</p>'
              f'<form method="post" action="/classroom">{token(req)}'
              f'<label>Student<select name="student_id" required>{options}</select></label>'
              '<label>Lesson title<input name="title" maxlength="150" required></label>'
              '<label>Scheduled time (UTC)<input name="scheduled_at" type="datetime-local" required></label>'
              '<label>Video meeting link<input name="meeting_url" type="url" maxlength="2000" required></label>'
              '<label>Lesson notes<textarea name="notes" maxlength="3000"></textarea></label>'
              '<button>Create classroom</button></form></article>'
              f'<article><h2>Classrooms</h2><ul>{listing or "<li>No classrooms yet.</li>"}</ul></article>')
        return page("Live Classroom",body)

    @app.post("/classroom")
    def create_classroom(req: Request,student_id:str=Form(...),title:str=Form(...),
                         scheduled_at:str=Form(...),meeting_url:str=Form(...),
                         notes:str=Form(""),csrf:str=Form(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        try:
            student_id=str(UUID(student_id))
        except ValueError:
            raise HTTPException(400,"Invalid student")
        title,notes,meeting_url=title.strip(),notes.strip(),meeting_url.strip()
        if not 1<=len(title)<=150 or len(notes)>3000 or not valid_meeting_url(meeting_url):
            raise HTTPException(400,"Invalid classroom details or video link")
        try:
            when=datetime.strptime(scheduled_at,"%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400,"Invalid scheduled time")
        if when<=datetime.now(timezone.utc):
            raise HTTPException(400,"Choose a future time")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""INSERT INTO public.classroom_rooms
                (teacher_id,student_id,title,meeting_url,scheduled_at,notes)
                SELECT ts.teacher_id,ts.student_id,%s,%s,%s,%s
                FROM public.teacher_students ts
                WHERE ts.teacher_id=%s AND ts.student_id=%s RETURNING id""",
                (title,meeting_url,when,notes,teacher["id"],student_id))
            row=cur.fetchone()
            if not row:
                raise HTTPException(403,"Student is not assigned to this teacher")
        return RedirectResponse(f"/classroom/{row[0]}",status_code=303)

    @app.get("/my-classroom")
    def student_classrooms(req: Request):
        student=require(req,"student")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT r.id,r.title,r.scheduled_at FROM public.classroom_rooms r
                JOIN public.teacher_students ts ON ts.teacher_id=r.teacher_id AND ts.student_id=r.student_id
                WHERE r.student_id=%s ORDER BY r.scheduled_at DESC""",(student["id"],))
            rooms=cur.fetchall()
        listing="".join(f'<li><a href="/classroom/{rid}">{E(title)}</a> — {E(when)} UTC</li>'
                        for rid,title,when in rooms)
        return page("My Classroom",'<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>My online lessons</h2><ul>{listing or "<li>No classroom sessions yet.</li>"}</ul></article>')

    @app.get("/classroom/{room_id}")
    def classroom_room(req: Request,room_id:int):
        u=viewer(req)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT r.title,r.scheduled_at,r.notes,r.meeting_url,r.student_id,s.display_name
                FROM public.classroom_rooms r
                JOIN public.teacher_students ts ON ts.teacher_id=r.teacher_id AND ts.student_id=r.student_id
                JOIN public.student_profiles s ON s.id=r.student_id
                WHERE r.id=%s AND ((r.teacher_id=%s AND %s='teacher')
                                   OR (r.student_id=%s AND %s='student'))""",
                (room_id,u["id"],u["role"],u["id"],u["role"]))
            room=cur.fetchone()
        if not room:
            raise HTTPException(404,"Classroom not found")
        title,when,notes,url,student_id,name=room
        back="/classroom" if u["role"]=="teacher" else "/my-classroom"
        body=(f'<p><a href="{back}">← Classrooms</a></p><article><h2>{E(title)}</h2>'
              f'<p>Student: {E(name)} · Scheduled: {E(when)} UTC</p><p>{E(notes)}</p>'
              f'<p><a href="{E(url)}" target="_blank" rel="noopener noreferrer">Join video meeting</a></p>'
              f'<p><a href="/whiteboard/{student_id}">Open shared whiteboard</a></p>'
              '<p>Whiteboard changes are saved but do not yet sync live between browsers.</p></article>')
        return page("Classroom Session",body)
