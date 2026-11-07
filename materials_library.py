"""Private teaching materials library for the Biology Studio portal."""
import secrets
from pathlib import Path
from fastapi import Request, Form, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

STORE = Path(__file__).with_name("private_materials")
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".pptx", ".docx"}

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES users(id)
        )""")

    @app.get("/materials")
    def materials(req: Request):
        u = require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            items = c.execute("""SELECT m.*, u.display FROM materials m
                JOIN users u ON u.id=m.student_id ORDER BY m.id DESC""").fetchall()
        options = "".join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        listing = "".join(
            f'<li><a href="/materials/{m["id"]}/download">{E(m["title"])}</a> '
            f'— {E(m["display"])} ({E(m["original_name"])}) '
            f'<form method="post" action="/materials/{m["id"]}/delete" style="display:inline">'
            f'{token(req)}<button type="submit">Delete</button></form></li>'
            for m in items
        )
        body = (
            '<p><a href="/teacher">← Teacher dashboard</a></p>'
            '<article><h2>Upload learning material</h2>'
            '<p>PDF, PNG, JPG, PPTX or DOCX · maximum 10 MB. Each upload is assigned to one student.</p>'
            f'<form action="/materials" method="post" enctype="multipart/form-data">{token(req)}'
            '<label>Title<input name="title" maxlength="150" required></label>'
            f'<label>Student<select name="student_id" required>{options}</select></label>'
            '<label>File<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.pptx,.docx" required></label>'
            '<button type="submit">Upload material</button></form></article>'
            f'<article><h2>Shared materials</h2><ul>{listing or "<li>No materials yet.</li>"}</ul></article>'
        )
        return page("Materials Library", body)

    @app.post("/materials")
    async def upload_material(req: Request, title: str = Form(...), student_id: int = Form(...),
                              csrf: str = Form(...), file: UploadFile = File(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title = title.strip()
        original = Path((file.filename or "").replace("\\", "/")).name
        suffix = Path(original).suffix.lower()
        if not title or len(title) > 150 or suffix not in ALLOWED:
            raise HTTPException(400, "Invalid title or unsupported file type")
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
                raise HTTPException(400, "Choose a valid student")
        data = await file.read(MAX_BYTES + 1)
        await file.close()
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(413, "File must be between 1 byte and 10 MB")
        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise HTTPException(400, "Invalid PDF file")
        if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(400, "Invalid PNG file")
        if suffix in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
            raise HTTPException(400, "Invalid JPEG file")
        if suffix in {".pptx", ".docx"} and not data.startswith(b"PK\x03\x04"):
            raise HTTPException(400, "Invalid Office document")
        STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
        stored = secrets.token_hex(24) + suffix
        path = STORE / stored
        path.write_bytes(data)
        try:
            with conn() as c:
                c.execute("INSERT INTO materials(student_id,title,original_name,stored_name) VALUES(?,?,?,?)",
                          (student_id, title, original[:255], stored))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return RedirectResponse("/materials", status_code=303)

    @app.get("/materials/{material_id}/download")
    def download_material(req: Request, material_id: int):
         # A signed-in teacher can access assigned materials; students only their own.
        from_user = _current_user(req, conn)
        if not from_user:
            raise HTTPException(401, "Sign in required")
        with conn() as c:
            m = c.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if not m:
            raise HTTPException(404)
        if from_user["role"] != "teacher" and not (from_user["role"] == "student" and from_user["id"] == m["student_id"]):
            raise HTTPException(403, "Access denied")
        path = STORE / m["stored_name"]
        if not path.is_file():
            raise HTTPException(404, "File missing")
        return FileResponse(path, filename=m["original_name"], media_type="application/octet-stream")

    @app.post("/materials/{material_id}/delete")
    def delete_material(req: Request, material_id: int, csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        with conn() as c:
            m = c.execute("SELECT stored_name FROM materials WHERE id=?", (material_id,)).fetchone()
            if not m:
                raise HTTPException(404)
            c.execute("DELETE FROM materials WHERE id=?", (material_id,))
        (STORE / m["stored_name"]).unlink(missing_ok=True)
        return RedirectResponse("/materials", status_code=303)

    @app.get("/my-materials")
    def my_materials(req: Request):
        u = require(req, "student")
        with conn() as c:
            items = c.execute("SELECT * FROM materials WHERE student_id=? ORDER BY id DESC", (u["id"],)).fetchall()
        listing = "".join(
            f'<li><a href="/materials/{m["id"]}/download">{E(m["title"])}</a> — {E(m["original_name"])}</li>'
            for m in items
        )
        return page("My Materials", '<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>Learning materials</h2><ul>{listing or "<li>No shared materials yet.</li>"}</ul></article>')

def _current_user(req, conn):
    uid = req.session.get("uid")
    if not isinstance(uid, int):
        return None
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
