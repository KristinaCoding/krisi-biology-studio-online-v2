"""Interactive biology multiple-choice activities with saved attempts."""
import json
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS biology_activities (
            id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL, topic TEXT NOT NULL, questions TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS biology_activity_results (
            id INTEGER PRIMARY KEY, activity_id INTEGER NOT NULL UNIQUE REFERENCES biology_activities(id),
            student_id INTEGER NOT NULL REFERENCES users(id), answers TEXT NOT NULL,
            score INTEGER NOT NULL, total INTEGER NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    def get_activity(activity_id):
        with conn() as c:
            activity = c.execute("SELECT * FROM biology_activities WHERE id=?", (activity_id,)).fetchone()
        if not activity:
            raise HTTPException(404, "Activity not found")
        return activity

    def authorize(req, activity):
        uid = req.session.get("uid")
        if not isinstance(uid, int):
            raise HTTPException(401, "Sign in required")
        with conn() as c:
            viewer = c.execute("SELECT id,role FROM users WHERE id=?", (uid,)).fetchone()
        if not viewer:
            raise HTTPException(401)
        if viewer["role"] != "teacher" and not (viewer["role"] == "student" and viewer["id"] == activity["student_id"]):
            raise HTTPException(403)
        return viewer

    @app.get("/activities")
    def teacher_activities(req: Request):
        require(req, "teacher")
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            activities = c.execute("""SELECT a.*, u.display, r.score, r.total
                FROM biology_activities a JOIN users u ON u.id=a.student_id
                LEFT JOIN biology_activity_results r ON r.activity_id=a.id
                ORDER BY a.id DESC""").fetchall()
        options = ''.join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        listing = ''.join(f'<li><a href="/activities/{a["id"]}">{E(a["title"])}</a> — '
                          f'{E(a["display"])} · {E(a["topic"])} · '
                          f'{"Not completed" if a["score"] is None else str(a["score"]) + "/" + str(a["total"])}'
                          '</li>' for a in activities)
        body = (
            '<p><a href="/teacher">← Teacher dashboard</a></p>'
            '<article><h2>Create a biology activity</h2>'
            '<p>Add 1–10 multiple-choice questions. Separate the question and its four options using the fields below.</p>'
            f'<form method="post" action="/activities">{token(req)}'
            f'<label>Student<select name="student_id" required>{options}</select></label>'
            '<label>Activity title<input name="title" maxlength="150" required></label>'
            '<label>Topic<input name="topic" maxlength="100" required placeholder="e.g. Cell biology"></label>'
            '<label>Questions (JSON array)<textarea name="questions" rows="12" required '
            'placeholder=\'[{"question":"Which organelle produces ATP?","options":["Nucleus","Mitochondrion","Ribosome","Golgi apparatus"],"answer":1}]\'></textarea></label>'
            '<p>Each question needs a question, exactly four options and answer index 0–3.</p>'
            '<button type="submit">Create activity</button></form></article>'
            f'<article><h2>Assigned activities</h2><ul>{listing or "<li>No activities yet.</li>"}</ul></article>'
        )
        return page("Interactive Biology Activities", body)

    @app.post("/activities")
    def create_activity(req: Request, student_id: int = Form(...), title: str = Form(...),
                        topic: str = Form(...), questions: str = Form(...), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title, topic = title.strip(), topic.strip()
        if not title or len(title) > 150 or not topic or len(topic) > 100 or len(questions) > 20000:
            raise HTTPException(400, "Invalid activity details")
        try:
            data = json.loads(questions)
        except (ValueError, TypeError):
            raise HTTPException(400, "Questions must be valid JSON")
        if not isinstance(data, list) or not 1 <= len(data) <= 10:
            raise HTTPException(400, "Provide 1–10 questions")
        for q in data:
            if (not isinstance(q, dict) or set(q) != {"question", "options", "answer"}
                or not isinstance(q["question"], str) or not 1 <= len(q["question"].strip()) <= 500
                or not isinstance(q["options"], list) or len(q["options"]) != 4
                or any(not isinstance(opt, str) or not 1 <= len(opt.strip()) <= 250 for opt in q["options"])
                or type(q["answer"]) is not int or q["answer"] not in range(4)):
                raise HTTPException(400, "Each question needs four options and an answer index 0–3")
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
                raise HTTPException(400, "Choose a valid student")
            cur = c.execute("""INSERT INTO biology_activities(student_id,title,topic,questions)
                VALUES(?,?,?,?)""", (student_id, title, topic, json.dumps(data)))
            activity_id = cur.lastrowid
        return RedirectResponse(f"/activities/{activity_id}", status_code=303)

    @app.get("/my-activities")
    def student_activities(req: Request):
        u = require(req, "student")
        with conn() as c:
            rows = c.execute("""SELECT a.*, r.score, r.total FROM biology_activities a
                LEFT JOIN biology_activity_results r ON r.activity_id=a.id
                WHERE a.student_id=? ORDER BY a.id DESC""", (u["id"],)).fetchall()
        links = ''.join(f'<li><a href="/activities/{a["id"]}">{E(a["title"])}</a> — '
                        f'{E(a["topic"])} · '
                        f'{"Ready to complete" if a["score"] is None else "Completed: " + str(a["score"]) + "/" + str(a["total"])}'
                        '</li>' for a in rows)
        return page("My Biology Activities", '<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>Interactive exercises</h2><ul>{links or "<li>No activities assigned.</li>"}</ul></article>')

    @app.get("/activities/{activity_id}")
    def activity_detail(req: Request, activity_id: int):
        activity = get_activity(activity_id)
        viewer = authorize(req, activity)
        questions = json.loads(activity["questions"])
        with conn() as c:
            result = c.execute("SELECT * FROM biology_activity_results WHERE activity_id=?", (activity_id,)).fetchone()
        back = "/activities" if viewer["role"] == "teacher" else "/my-activities"
        if result:
            answers = json.loads(result["answers"])
            lines = ''.join(
                f'<li>{E(q["question"])} — '
                f'Answer: {E(q["options"][q["answer"]])}; '
                f'Selected: {E(q["options"][answers[i]])}</li>'
                for i, q in enumerate(questions)
            )
            body = (f'<p><a href="{back}">← Activities</a></p>'
                    f'<article><h2>{E(activity["title"])}</h2><p>{E(activity["topic"])}</p>'
                    f'<h3>Result: {result["score"]}/{result["total"]}</h3><ol>{lines}</ol></article>')
        elif viewer["role"] == "teacher":
            body = (f'<p><a href="{back}">← Activities</a></p>'
                    f'<article><h2>{E(activity["title"])}</h2>'
                    '<p>Assigned to the student. Awaiting their first attempt.</p></article>')
        else:
            blocks = []
            for i, q in enumerate(questions):
                opts = ''.join(
                    f'<label style="display:block"><input type="radio" name="q{i}" value="{j}" required> {E(opt)}</label>'
                    for j, opt in enumerate(q["options"])
                )
                blocks.append(f'<fieldset><legend>{i+1}. {E(q["question"])}</legend>{opts}</fieldset>')
            body = (f'<p><a href="{back}">← Activities</a></p>'
                    f'<article><h2>{E(activity["title"])}</h2><p>{E(activity["topic"])}</p>'
                    f'<form method="post" action="/activities/{activity_id}/submit">{token(req)}'
                    + ''.join(blocks) + '<button type="submit">Submit answers</button></form></article>')
        return page("Biology Activity", body)

    @app.post("/activities/{activity_id}/submit")
    async def submit_activity(req: Request, activity_id: int):
        activity = get_activity(activity_id)
        viewer = authorize(req, activity)
        if viewer["role"] != "student":
            raise HTTPException(403)
        form = await req.form()
        verifycsrf(req, str(form.get("csrf", "")))
        questions = json.loads(activity["questions"])
        answers = []
        for i in range(len(questions)):
            value = form.get(f"q{i}")
            if not isinstance(value, str) or value not in ("0", "1", "2", "3"):
                raise HTTPException(400, "Answer all questions")
            answers.append(int(value))
        score = sum(answer == q["answer"] for answer, q in zip(answers, questions))
        with conn() as c:
            try:
                c.execute("""INSERT INTO biology_activity_results(activity_id,student_id,answers,score,total)
                    VALUES(?,?,?,?,?)""", (activity_id, viewer["id"], json.dumps(answers), score, len(questions)))
            except __import__("sqlite3").IntegrityError:
                raise HTTPException(409, "This activity has already been completed")
        return RedirectResponse(f"/activities/{activity_id}", status_code=303)
