"""Read-only PostgreSQL progress views, restricted to assigned students."""
from uuid import UUID
from fastapi import Request, HTTPException
from database import get_connection


def register(app, require, page, E):
    def overview(student_id, teacher_id=None):
        with get_connection() as db, db.cursor() as cur:
            cur.execute("""SELECT s.display_name FROM public.student_profiles s
                WHERE s.id=%s AND (%s::uuid IS NULL OR EXISTS
                    (SELECT 1 FROM public.teacher_students ts
                     WHERE ts.teacher_id=%s AND ts.student_id=s.id))""",
                (student_id,teacher_id,teacher_id))
            student=cur.fetchone()
            if not student:
                raise HTTPException(404, "Student not found")
            cur.execute("""SELECT q.title,r.score,r.total FROM public.quizzes q
                LEFT JOIN public.quiz_results r ON r.quiz_id=q.id AND r.student_id=q.student_id
                WHERE q.student_id=%s ORDER BY q.title""",(student_id,))
            quizzes=cur.fetchall()
            cur.execute("""SELECT h.title,h.due_at,s.submitted_at,s.grade,s.feedback
                FROM public.homework h LEFT JOIN public.homework_submissions s
                ON s.homework_id=h.id AND s.student_id=h.student_id
                WHERE h.student_id=%s ORDER BY h.id DESC""",(student_id,))
            homework=cur.fetchall()
            cur.execute("""SELECT a.title,r.score,r.total FROM public.biology_activities a
                LEFT JOIN public.biology_activity_results r ON r.activity_id=a.id
                WHERE a.student_id=%s ORDER BY a.id DESC""",(student_id,))
            activities=cur.fetchall()
        done=[(score,total) for _,score,total in quizzes if score is not None and total is not None]
        total_points=sum(total for _,total in done)
        average=f"{sum(score for score,_ in done)/total_points*100:.1f}%" if total_points else "N/A"
        stats=('<div class="dashboard-stats">'
               f'<div class="stat-card"><strong>{len(done)}/{len(quizzes)}</strong><span>Quizzes completed</span></div>'
               f'<div class="stat-card"><strong>{average}</strong><span>Quiz points earned</span></div>'
               f'<div class="stat-card"><strong>{sum(1 for h in homework if h[2])}/{len(homework)}</strong><span>Homework submitted</span></div>'
               f'<div class="stat-card"><strong>{sum(1 for h in homework if h[3])}</strong><span>Homework graded</span></div></div>')
        quiz_rows="".join(f'<tr><td>{E(title)}</td><td>{E(str(score)+"/"+str(total)) if score is not None else "Not completed"}</td></tr>' for title,score,total in quizzes)
        activity_rows="".join(f'<tr><td>{E(title)}</td><td>{E(str(score)+"/"+str(total)) if score is not None else "Not completed"}</td></tr>' for title,score,total in activities)
        homework_rows="".join(f'<tr><td>{E(title)}</td><td>{E(due)}</td><td>{"Submitted" if submitted else "Not submitted"}</td><td>{E(grade) if grade else "Not graded"}</td><td>{E(feedback)}</td></tr>' for title,due,submitted,grade,feedback in homework)
        return (f'<h2>{E(student[0])}</h2>'+stats
                +'<article><h2>Interactive biology activities</h2><table><thead><tr><th>Activity</th><th>Score</th></tr></thead><tbody>'
                +(activity_rows or '<tr><td colspan="2">No activities assigned.</td></tr>')+'</tbody></table></article>'
                +'<article><h2>Quiz results</h2><table><thead><tr><th>Quiz</th><th>Score</th></tr></thead><tbody>'
                +(quiz_rows or '<tr><td colspan="2">No quizzes assigned.</td></tr>')+'</tbody></table></article>'
                +'<article><h2>Homework progress</h2><table><thead><tr><th>Homework</th><th>Due (UTC)</th><th>Status</th><th>Grade</th><th>Feedback</th></tr></thead><tbody>'
                +(homework_rows or '<tr><td colspan="5">No homework assigned.</td></tr>')+'</tbody></table></article>')

    @app.get("/progress")
    def teacher_progress(req: Request):
        teacher=require(req,"teacher")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""",(teacher["id"],))
            students=cur.fetchall()
        links="".join(f'<li><a href="/progress/{sid}">{E(name)}</a></li>' for sid,name in students)
        return page("Student Progress",'<p><a href="/teacher">← Teacher dashboard</a></p>'
                    f'<article><h2>Students</h2><ul>{links or "<li>No students yet.</li>"}</ul></article>')

    @app.get("/progress/{student_id}")
    def teacher_student_progress(req: Request, student_id: str):
        teacher=require(req,"teacher")
        try:
            student_id=str(UUID(student_id))
        except ValueError:
            raise HTTPException(404,"Student not found")
        return page("Student Progress",'<p><a href="/progress">← All students</a></p>'
                    +overview(student_id,teacher["id"]))

    @app.get("/my-progress")
    def my_progress(req: Request):
        student=require(req,"student")
        return page("My Progress",'<p><a href="/student">← Student dashboard</a></p>'
                    +overview(student["id"]))
