"""Private per-student shared whiteboards, persisted in PostgreSQL."""
import json
from uuid import UUID
from database import get_connection
from psycopg.types.json import Jsonb
from fastapi import Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

MAX_STROKES = 1200
MAX_POINTS = 300
MAX_BYTES = 250000

def register(app, conn, require, page, token, verifycsrf, E):
    def allowed(req, student_id):
        try:
            sid=str(UUID(str(student_id)))
        except (ValueError,TypeError):
            raise HTTPException(404,"Student not found")
        from auth_service import get_user_role
        raw=req.session.get("supabase_user_id")
        try:
            uid=str(UUID(str(raw)))
        except (ValueError,TypeError):
            raise HTTPException(401,"Sign in required")
        role=get_user_role(uid)
        if role not in ("teacher","student"):
            raise HTTPException(403)
        viewer=require(req,role)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""
                SELECT s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE s.id=%s AND
                    ((ts.teacher_id=%s AND %s='teacher')
                    OR (s.id=%s AND %s='student'))
                LIMIT 1
            """,(sid,viewer["id"],role,viewer["id"],role))
            row=cur.fetchone()
        if row is None:
            raise HTTPException(404,"Board not found")
        return {"id":sid,"display":row[0]}

    @app.get("/whiteboard")
    def teacher_boards(req: Request):
        require(req, "teacher")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""",(require(req,"teacher")["id"],))
            students=[{"id":sid,"display":name} for sid,name in cur.fetchall()]
        links = "".join(f'<li><a href="/whiteboard/{s["id"]}">{E(s["display"])}</a></li>' for s in students)
        return page("Shared Whiteboards", '<p><a href="/teacher">← Teacher dashboard</a></p>'
                    f'<article><h2>Choose a student board</h2><ul>{links or "<li>No students yet.</li>"}</ul></article>')

    @app.get("/my-whiteboard")
    def my_board(req: Request):
        u = require(req, "student")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f'/whiteboard/{u["id"]}', status_code=303)

    @app.get("/whiteboard/{student_id}")
    def board(req: Request, student_id: str):
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
    def get_board(req: Request, student_id: str):
        allowed(req, student_id)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("SELECT strokes,updated_at FROM public.whiteboards WHERE student_id=%s",(student_id,))
            result=cur.fetchone()
            row={"strokes":result[0],"updated_at":result[1].isoformat()} if result else None
        return JSONResponse({"strokes": (json.loads(row["strokes"]) if isinstance(row["strokes"],str) else row["strokes"]) if row else [],
                             "updated_at": row["updated_at"] if row else None})

    @app.post("/whiteboard/{student_id}/save")
    def save_board(req: Request, student_id: str, strokes: str = Form(...), csrf: str = Form(...)):
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
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""INSERT INTO public.whiteboards(student_id,strokes) VALUES(%s,%s)
                ON CONFLICT(student_id) DO UPDATE SET strokes=excluded.strokes,updated_at=now()""",
                (student_id,Jsonb(data)))
        return JSONResponse({"saved": True})
