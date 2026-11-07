"""PostgreSQL-backed biology activities; uses existing Supabase UUID identities."""
import json
from uuid import UUID
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from psycopg.types.json import Jsonb
from database import get_connection

def register(app, require, page, token, verifycsrf, E):
    def activity_for(viewer, activity_id):
        try:
            aid = int(activity_id)
        except (ValueError, TypeError):
            raise HTTPException(404, "Activity not found")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                SELECT a.id,a.teacher_id,a.student_id,a.title,a.topic,a.questions,
                       r.score,r.total,r.answers
                FROM public.biology_activities a
                JOIN public.teacher_students ts
                  ON ts.teacher_id=a.teacher_id AND ts.student_id=a.student_id
                LEFT JOIN public.biology_activity_results r ON r.activity_id=a.id
                WHERE a.id=%s AND
                  (a.teacher_id=%s AND %s='teacher' OR
                   a.student_id=%s AND %s='student')
            """, (aid,viewer["id"],viewer["role"],viewer["id"],viewer["role"]))
            row=cur.fetchone()
        if row is None: raise HTTPException(404,"Activity not found")
        return dict(zip(("id","teacher_id","student_id","title","topic","questions","score","total","answers"),row))

    @app.get("/activities")
    def teacher_activities(req: Request):
        teacher=require(req,"teacher")
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""
                SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name
            """,(teacher["id"],))
            students=cur.fetchall()
            cur.execute("""
                SELECT a.id,a.title,a.topic,s.display_name,r.score,r.total
                FROM public.biology_activities a
                JOIN public.teacher_students ts ON ts.teacher_id=a.teacher_id AND ts.student_id=a.student_id
                JOIN public.student_profiles s ON s.id=a.student_id
                LEFT JOIN public.biology_activity_results r ON r.activity_id=a.id
                WHERE a.teacher_id=%s ORDER BY a.id DESC
            """,(teacher["id"],))
            activities=cur.fetchall()
        options="".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        rows="".join(f'<li><a href="/activities/{aid}">{E(title)}</a> — {E(name)} · {E(topic)} · {score if score is not None else "Pending"}{"/"+str(total) if score is not None else ""}</li>' for aid,title,topic,name,score,total in activities)
        body=(f'<p><a href="/teacher">← Dashboard</a></p><article><h2>Create biology activity</h2>'
              f'<form method="post">{token(req)}<label>Student<select name="student_id" required>{options}</select></label>'
              '<label>Title<input name="title" maxlength="150" required></label>'
              '<label>Topic<input name="topic" maxlength="100" required></label>'
              '<label>Questions JSON<textarea name="questions" maxlength="20000" rows="10" required></textarea></label>'
              '<p>JSON array of 1–10 questions with question, four options, and answer index (0–3).</p>'
              '<button>Create activity</button></form></article>'
              f'<article><h2>Assigned activities</h2><ul>{rows or "<li>No activities</li>"}</ul></article>')
        return page("Biology activities",body)

    @app.post("/activities")
    def create(req:Request,student_id:str=Form(...),title:str=Form(...),topic:str=Form(...),questions:str=Form(...),csrf:str=Form(...)):
        teacher=require(req,"teacher");verifycsrf(req,csrf)
        title=title.strip();topic=topic.strip()
        if not 1<=len(title)<=150 or not 1<=len(topic)<=100 or len(questions)>20000:
            raise HTTPException(400,"Invalid activity")
        try:
            student=str(UUID(student_id));data=json.loads(questions)
        except (ValueError,TypeError):
            raise HTTPException(400,"Invalid student or JSON")
        if not isinstance(data,list) or not 1<=len(data)<=10:
            raise HTTPException(400,"Provide 1–10 questions")
        for q in data:
            if (not isinstance(q,dict) or set(q)!={"question","options","answer"}
                or not isinstance(q["question"],str) or not 1<=len(q["question"].strip())<=500
                or not isinstance(q["options"],list) or len(q["options"])!=4
                or any(not isinstance(o,str) or not 1<=len(o.strip())<=250 for o in q["options"])
                or type(q["answer"]) is not int or q["answer"] not in range(4)):
                raise HTTPException(400,"Invalid question")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""
                INSERT INTO public.biology_activities(teacher_id,student_id,title,topic,questions)
                SELECT ts.teacher_id,ts.student_id,%s,%s,%s
                FROM public.teacher_students ts
                WHERE ts.teacher_id=%s AND ts.student_id=%s
                RETURNING id
            """,(title,topic,Jsonb(data),teacher["id"],student))
            row=cur.fetchone()
            if row is None: raise HTTPException(403,"Student is not assigned to this teacher")
        return RedirectResponse(f"/activities/{row[0]}",status_code=303)

    @app.get("/my-activities")
    def mine(req:Request):
        student=require(req,"student")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""
                SELECT a.id,a.title,a.topic,r.score,r.total
                FROM public.biology_activities a
                JOIN public.teacher_students ts ON ts.teacher_id=a.teacher_id AND ts.student_id=a.student_id
                LEFT JOIN public.biology_activity_results r ON r.activity_id=a.id
                WHERE a.student_id=%s ORDER BY a.id DESC
            """,(student["id"],))
            rows=cur.fetchall()
        listing="".join(f'<li><a href="/activities/{aid}">{E(title)}</a> — {E(topic)} · {score if score is not None else "Ready"}{"/"+str(total) if score is not None else ""}</li>' for aid,title,topic,score,total in rows)
        return page("My activities",f'<p><a href="/student">← Dashboard</a></p><article><ul>{listing or "<li>No activities</li>"}</ul></article>')

    @app.get("/activities/{activity_id}")
    def detail(req:Request,activity_id:int):
        # Use the portal's verified identity; never trust a role supplied by the browser.
        from auth_service import get_user_role
        raw=req.session.get("supabase_user_id")
        try: uid=str(UUID(str(raw)))
        except (ValueError,TypeError): raise HTTPException(401)
        role=get_user_role(uid)
        if role not in ("teacher","student"): raise HTTPException(403)
        viewer={"id":uid,"role":role}
        a=activity_for(viewer,activity_id)
        questions=a["questions"]
        if isinstance(questions,str):questions=json.loads(questions)
        back="/activities" if role=="teacher" else "/my-activities"
        if a["score"] is not None:
            body=f'<article><h2>{E(a["title"])}</h2><p>Score: {a["score"]}/{a["total"]}</p></article>'
        elif role=="teacher":
            body=f'<article><h2>{E(a["title"])}</h2><p>Awaiting student submission.</p></article>'
        else:
            fields=""
            for i,q in enumerate(questions):
                opts="".join(f'<label><input type="radio" name="q{i}" value="{j}" required> {E(o)}</label>' for j,o in enumerate(q["options"]))
                fields+=f'<fieldset><legend>{i+1}. {E(q["question"])}</legend>{opts}</fieldset>'
            body=f'<article><h2>{E(a["title"])}</h2><form method="post" action="/activities/{activity_id}/submit">{token(req)}{fields}<button>Submit</button></form></article>'
        return page("Biology activity",f'<p><a href="{back}">← Activities</a></p>'+body)

    @app.post("/activities/{activity_id}/submit")
    async def submit(req:Request,activity_id:int):
        student=require(req,"student")
        a=activity_for(student,activity_id)
        if a["score"] is not None:raise HTTPException(409,"Already submitted")
        form=await req.form();verifycsrf(req,str(form.get("csrf","")))
        questions=a["questions"]
        if isinstance(questions,str):questions=json.loads(questions)
        answers=[]
        for i in range(len(questions)):
            v=form.get(f"q{i}")
            if not isinstance(v,str) or v not in ("0","1","2","3"):
                raise HTTPException(400,"Answer all questions")
            answers.append(int(v))
        score=sum(answer==q["answer"] for answer,q in zip(answers,questions))
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""
                INSERT INTO public.biology_activity_results(activity_id,student_id,answers,score,total)
                SELECT a.id,a.student_id,%s,%s,%s
                FROM public.biology_activities a
                JOIN public.teacher_students ts ON ts.teacher_id=a.teacher_id AND ts.student_id=a.student_id
                WHERE a.id=%s AND a.student_id=%s
                ON CONFLICT(activity_id) DO NOTHING RETURNING id
            """,(Jsonb(answers),score,len(questions),activity_id,student["id"]))
            if cur.fetchone() is None:raise HTTPException(409,"Already submitted or not assigned")
        return RedirectResponse(f"/activities/{activity_id}",status_code=303)
