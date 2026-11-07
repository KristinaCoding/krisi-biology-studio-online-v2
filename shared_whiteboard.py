"""Private per-student shared whiteboards, persisted in SQLite."""
import json
from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

MAX_STROKES = 1200
MAX_POINTS = 300
MAX_BYTES = 250000

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS whiteboards (
            student_id INTEGER PRIMARY KEY REFERENCES users(id),
            strokes TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    def allowed(req, student_id):
        uid = req.session.get("uid")
        if not isinstance(uid, int):
            raise HTTPException(401, "Sign in required")
        with conn() as c:
            viewer = c.execute("SELECT id,role FROM users WHERE id=?", (uid,)).fetchone()
            student = c.execute("SELECT id,display FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
        if not viewer:
            raise HTTPException(401)
        if not student:
            raise HTTPException(404)
        if viewer["role"] != "teacher" and not (viewer["role"] == "student" and viewer["id"] == student_id):
            raise HTTPException(403)
        return student

    @app.get("/whiteboard")
    def teacher_boards(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
        links = "".join(f'<li><a href="/whiteboard/{s["id"]}">{E(s["display"])}</a></li>' for s in students)
        return page("Shared Whiteboards", '<p><a href="/teacher">← Teacher dashboard</a></p>'
                    f'<article><h2>Choose a student board</h2><ul>{links or "<li>No students yet.</li>"}</ul></article>')

    @app.get("/my-whiteboard")
    def my_board(req: Request):
        u = require(req, "student")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f'/whiteboard/{u["id"]}', status_code=303)

    @app.get("/whiteboard/{student_id}")
    def board(req: Request, student_id: int):
        student = allowed(req, student_id)
        csrf = token(req)
        # Canvas script is served as a static file, never interpolated from user input.
        body = ('<p><a href="/">← Dashboard</a></p>'
                f'<article><h2>Shared board · {E(student["display"])}</h2>'
                '<p>Draw with your mouse or touchscreen. Refreshing the board loads the latest saved version.</p>'
                f'<div id="wb-root" data-student-id="{student_id}">{csrf}'
                '<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem">'
                '<label>Ink <input id="wb-color" type="color" value="#d6c2ff"></label>'
                '<button id="wb-undo" type="button">Undo</button>'
                '<button id="wb-clear" type="button">Clear board</button>'
                '<button id="wb-save" type="button">Save changes</button>'
                '<button id="wb-reload" type="button">Reload</button></div>'
                '<canvas id="wb-canvas" width="900" height="520" '
                'style="width:100%;height:auto;touch-action:none;background:#1d1b20;border:1px solid #887f91;border-radius:8px"></canvas>'
                '<p id="wb-status" role="status">Loading board…</p></div></article>'
                '<script src="/static/shared_whiteboard.js" defer></script>')
        return page("Shared Whiteboard", body)

    @app.get("/whiteboard/{student_id}/data")
    def get_board(req: Request, student_id: int):
        allowed(req, student_id)
        with conn() as c:
            row = c.execute("SELECT strokes,updated_at FROM whiteboards WHERE student_id=?", (student_id,)).fetchone()
        return JSONResponse({"strokes": json.loads(row["strokes"]) if row else [],
                             "updated_at": row["updated_at"] if row else None})

    @app.post("/whiteboard/{student_id}/save")
    def save_board(req: Request, student_id: int, strokes: str = Form(...), csrf: str = Form(...)):
        allowed(req, student_id)
        verifycsrf(req, csrf)
        if len(strokes.encode("utf-8")) > MAX_BYTES:
            raise HTTPException(413, "Board too large")
        try:
            data = json.loads(strokes)
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid drawing")
        if not isinstance(data, list) or len(data) > MAX_STROKES:
            raise HTTPException(400, "Too many strokes")
        for stroke in data:
            if not isinstance(stroke, dict) or set(stroke) != {"color", "points"}:
                raise HTTPException(400, "Invalid stroke")
            color, points = stroke["color"], stroke["points"]
            if not isinstance(color, str) or len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
                raise HTTPException(400, "Invalid color")
            if not isinstance(points, list) or not (1 <= len(points) <= MAX_POINTS):
                raise HTTPException(400, "Invalid points")
            for point in points:
                if (not isinstance(point, list) or len(point) != 2 or
                    any(type(v) not in (int, float) or not (0 <= v <= 900 if i == 0 else 0 <= v <= 520) for i, v in enumerate(point))):
                    raise HTTPException(400, "Invalid coordinates")
        with conn() as c:
            c.execute("""INSERT INTO whiteboards(student_id,strokes) VALUES(?,?)
                ON CONFLICT(student_id) DO UPDATE SET strokes=excluded.strokes,updated_at=CURRENT_TIMESTAMP""",
                (student_id, json.dumps(data, separators=(",", ":"))))
        return JSONResponse({"saved": True})
