"""PostgreSQL-backed certificates, scoped to assigned teachers and students."""
import secrets
from uuid import UUID
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from database import get_connection


def register(app, require, page, token, verifycsrf, E):
    def current(req):
        from auth_service import get_user_role
        try:
            uid = str(UUID(str(req.session.get("supabase_user_id"))))
        except (TypeError, ValueError):
            raise HTTPException(401, "Sign in required")
        role = get_user_role(uid)
        if role not in ("teacher", "student"):
            raise HTTPException(403, "Access denied")
        return require(req, role)

    @app.get("/certificates")
    def teacher_certificates(req: Request):
        teacher = require(req, "teacher")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""", (teacher["id"],))
            students = cur.fetchall()
            cur.execute("""SELECT c.id,c.title,s.display_name,c.issued_on
                FROM public.certificates c
                JOIN public.teacher_students ts ON ts.teacher_id=c.teacher_id AND ts.student_id=c.student_id
                JOIN public.student_profiles s ON s.id=c.student_id
                WHERE c.teacher_id=%s ORDER BY c.id DESC""", (teacher["id"],))
            certificates = cur.fetchall()
        options = "".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        rows = "".join(
            f'<li><a href="/certificates/{cid}">{E(title)}</a> — {E(name)} — {E(issued)} '
            f'<form method="post" action="/certificates/{cid}/delete" style="display:inline">'
            f'{token(req)}<button type="submit">Revoke</button></form></li>'
            for cid,title,name,issued in certificates)
        body = ('<p><a href="/teacher">← Teacher dashboard</a></p>'
                '<article><h2>Issue certificate</h2>'
                f'<form method="post" action="/certificates">{token(req)}'
                f'<label>Student<select name="student_id" required>{options}</select></label>'
                '<label>Certificate title<input name="title" maxlength="150" required></label>'
                '<label>Achievement details<textarea name="description" maxlength="2000"></textarea></label>'
                '<button>Issue certificate</button></form></article>'
                f'<article><h2>Issued certificates</h2><ul>{rows or "<li>No certificates yet.</li>"}</ul></article>')
        return page("Certificates & Achievements", body)

    @app.post("/certificates")
    def issue_certificate(req: Request, student_id: str = Form(...), title: str = Form(...),
                          description: str = Form(""), csrf: str = Form(...)):
        teacher = require(req, "teacher")
        verifycsrf(req, csrf)
        try:
            student_id = str(UUID(student_id))
        except ValueError:
            raise HTTPException(400, "Invalid student")
        title, description = title.strip(), description.strip()
        if not 1 <= len(title) <= 150 or len(description) > 2000:
            raise HTTPException(400, "Invalid certificate details")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""INSERT INTO public.certificates
                (teacher_id,student_id,title,description,certificate_code)
                SELECT ts.teacher_id,ts.student_id,%s,%s,%s
                FROM public.teacher_students ts
                WHERE ts.teacher_id=%s AND ts.student_id=%s RETURNING id""",
                (title,description,secrets.token_hex(12).upper(),teacher["id"],student_id))
            if cur.fetchone() is None:
                raise HTTPException(403, "Student is not assigned to this teacher")
        return RedirectResponse("/certificates", status_code=303)

    @app.get("/my-certificates")
    def my_certificates(req: Request):
        student = require(req, "student")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""SELECT c.id,c.title,c.issued_on FROM public.certificates c
                JOIN public.teacher_students ts ON ts.teacher_id=c.teacher_id AND ts.student_id=c.student_id
                WHERE c.student_id=%s ORDER BY c.id DESC""", (student["id"],))
            items = cur.fetchall()
        links = "".join(f'<li><a href="/certificates/{cid}">{E(title)}</a> — issued {E(issued)}</li>'
                        for cid,title,issued in items)
        return page("My Certificates", '<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>My achievements</h2><ul>{links or "<li>No certificates yet.</li>"}</ul></article>')

    @app.get("/certificates/{certificate_id}")
    def view_certificate(req: Request, certificate_id: int):
        viewer = current(req)
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""SELECT c.title,c.description,c.issued_on,c.certificate_code,
                       s.display_name FROM public.certificates c
                JOIN public.teacher_students ts ON ts.teacher_id=c.teacher_id AND ts.student_id=c.student_id
                JOIN public.student_profiles s ON s.id=c.student_id
                WHERE c.id=%s AND ((c.teacher_id=%s AND %s='teacher')
                                 OR (c.student_id=%s AND %s='student'))""",
                (certificate_id,viewer["id"],viewer["role"],viewer["id"],viewer["role"]))
            item = cur.fetchone()
        if item is None:
            raise HTTPException(404, "Certificate not found")
        title,description,issued,code,name = item
        back = "/certificates" if viewer["role"] == "teacher" else "/my-certificates"
        body = ('<article class="certificate" style="text-align:center;padding:3rem">'
                '<p>KRISI BIOLOGY STUDIO · CERTIFICATE OF ACHIEVEMENT</p>'
                f'<h2>{E(title)}</h2><p>This certificate is awarded to</p>'
                f'<h2>{E(name)}</h2><p>{E(description)}</p>'
                f'<p>Issued on {E(issued)}</p><small>Certificate ID: {E(code)}</small>'
                '</article><p>Use your browser Print command to save as PDF.</p>'
                f'<p><a href="{back}">← Back to certificates</a></p>')
        return page("Certificate of Achievement", body)

    @app.post("/certificates/{certificate_id}/delete")
    def revoke_certificate(req: Request, certificate_id: int, csrf: str = Form(...)):
        teacher = require(req, "teacher")
        verifycsrf(req, csrf)
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""DELETE FROM public.certificates
                WHERE id=%s AND teacher_id=%s RETURNING id""",
                (certificate_id,teacher["id"]))
            if cur.fetchone() is None:
                raise HTTPException(404, "Certificate not found")
        return RedirectResponse("/certificates", status_code=303)
