"""Teacher-issued certificates and student achievements."""
import secrets
from datetime import date
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            issued_on TEXT NOT NULL,
            certificate_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    @app.get("/certificates")
    def teacher_certificates(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            certificates = c.execute("""SELECT c.*, u.display FROM certificates c
                JOIN users u ON u.id=c.student_id ORDER BY c.id DESC""").fetchall()
        options = "".join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        rows = "".join(
            f'<li><a href="/certificates/{item["id"]}">{E(item["title"])}</a>'
            f' — {E(item["display"])} — {E(item["issued_on"])}'
            f'<form method="post" action="/certificates/{item["id"]}/delete" style="display:inline">{token(req)}'
            '<button type="submit">Revoke</button></form></li>'
            for item in certificates
        )
        body = (
            '<p><a href="/teacher">← Teacher dashboard</a></p>'
            '<article><h2>Issue certificate</h2>'
            f'<form method="post" action="/certificates">{token(req)}'
            f'<label>Student<select name="student_id" required>{options}</select></label>'
            '<label>Certificate title<input name="title" maxlength="150" required></label>'
            '<label>Achievement details<textarea name="description" maxlength="2000"></textarea></label>'
            '<button type="submit">Issue certificate</button></form></article>'
            f'<article><h2>Issued certificates</h2><ul>{rows or "<li>No certificates issued yet.</li>"}</ul></article>'
        )
        return page("Certificates & Achievements", body)

    @app.post("/certificates")
    def issue_certificate(req: Request, student_id: int = Form(...), title: str = Form(...),
                          description: str = Form(""), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title, description = title.strip(), description.strip()
        if not title or len(title) > 150 or len(description) > 2000:
            raise HTTPException(400, "Invalid certificate details")
        with conn() as c:
            student = c.execute("SELECT id FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
            if not student:
                raise HTTPException(400, "Choose a valid student")
            c.execute("""INSERT INTO certificates(student_id,title,description,issued_on,certificate_code)
                VALUES(?,?,?,?,?)""", (student_id, title, description, date.today().isoformat(),
                                       secrets.token_hex(12).upper()))
        return RedirectResponse("/certificates", status_code=303)

    @app.get("/my-certificates")
    def my_certificates(req: Request):
        u = require(req, "student")
        with conn() as c:
            items = c.execute("SELECT * FROM certificates WHERE student_id=? ORDER BY id DESC", (u["id"],)).fetchall()
        links = "".join(
            f'<li><a href="/certificates/{item["id"]}">{E(item["title"])}</a>'
            f' — issued {E(item["issued_on"])}</li>' for item in items
        )
        return page("My Certificates", '<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>My achievements</h2><ul>{links or "<li>No certificates yet.</li>"}</ul></article>')

    @app.get("/certificates/{certificate_id}")
    def view_certificate(req: Request, certificate_id: int):
        uid = req.session.get("uid")
        if not isinstance(uid, int):
            raise HTTPException(401, "Sign in required")
        with conn() as c:
            viewer = c.execute("SELECT id,role FROM users WHERE id=?", (uid,)).fetchone()
            item = c.execute("""SELECT cert.*, u.display FROM certificates cert
                JOIN users u ON u.id=cert.student_id WHERE cert.id=?""", (certificate_id,)).fetchone()
        if not viewer:
            raise HTTPException(401, "Sign in required")
        if not item:
            raise HTTPException(404)
        if viewer["role"] != "teacher" and not (viewer["role"] == "student" and viewer["id"] == item["student_id"]):
            raise HTTPException(403, "Access denied")
        body = (
            '<article class="certificate" style="text-align:center;padding:3rem">'
            '<p>KRISI BIOLOGY STUDIO · CERTIFICATE OF ACHIEVEMENT</p>'
            f'<h2>{E(item["title"])}</h2>'
            '<p>This certificate is awarded to</p>'
            f'<h2>{E(item["display"])}</h2>'
            f'<p>{E(item["description"])}</p>'
            f'<p>Issued on {E(item["issued_on"])}</p>'
            f'<small>Certificate ID: {E(item["certificate_code"])}</small>'
            '</article>'
            '<p>Use your browser’s Print command to print or save this certificate as PDF.</p>'
            f'<p><a href="{"/certificates" if viewer["role"] == "teacher" else "/my-certificates"}">← Back to certificates</a></p>'
        )
        return page("Certificate of Achievement", body)

    @app.post("/certificates/{certificate_id}/delete")
    def revoke_certificate(req: Request, certificate_id: int, csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        with conn() as c:
            c.execute("DELETE FROM certificates WHERE id=?", (certificate_id,))
        return RedirectResponse("/certificates", status_code=303)
