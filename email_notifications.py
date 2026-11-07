"""PostgreSQL-backed teacher-scoped email outbox; sending is explicit."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from uuid import UUID
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from database import get_connection


def queue(recipient, subject, message, teacher_id=None):
    if not isinstance(recipient,str) or "@" not in recipient or not recipient.strip():
        return False
    if teacher_id is not None:
        try:
            teacher_id=str(UUID(str(teacher_id)))
        except (TypeError,ValueError):
            raise ValueError("Invalid teacher")
    with get_connection() as db,db.cursor() as cur:
        cur.execute("""INSERT INTO public.email_notifications
            (teacher_id,recipient,subject,message) VALUES(%s,%s,%s,%s)""",
            (teacher_id,recipient.strip(),str(subject)[:180],str(message)[:10000]))
    return True


def notify_student(student_id, subject, message, teacher_id):
    """Queue only if the teacher is currently assigned to the student."""
    with get_connection() as db,db.cursor() as cur:
        cur.execute("""SELECT au.email FROM auth.users au
            JOIN public.student_profiles sp ON sp.id=au.id
            JOIN public.teacher_students ts ON ts.student_id=sp.id
            WHERE ts.teacher_id=%s AND ts.student_id=%s""",(teacher_id,student_id))
        row=cur.fetchone()
    return queue(row[0],subject,message,teacher_id) if row and row[0] else False


def smtp_configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST","SMTP_PORT","SMTP_USER","SMTP_PASSWORD","SMTP_FROM"))


def deliver_pending(teacher_id,limit=20):
    """Manual send, only the invoking teacher's pending messages."""
    if not smtp_configured():
        return 0,"SMTP is not configured"
    try:
        port=int(os.environ["SMTP_PORT"])
    except ValueError:
        return 0,"Invalid SMTP_PORT"
    if port not in (465,587):
        return 0,"Use SMTP port 465 or 587"
    with get_connection() as db,db.cursor() as cur:
        cur.execute("""SELECT id,recipient,subject,message FROM public.email_notifications
            WHERE status='pending' AND teacher_id=%s ORDER BY id LIMIT %s""",(teacher_id,limit))
        items=cur.fetchall()
    sent=0
    for notification_id,recipient,subject,body in items:
        msg=EmailMessage()
        msg["From"]=os.environ["SMTP_FROM"]
        msg["To"]=recipient
        msg["Subject"]=subject
        msg.set_content(body)
        try:
            if port==465:
                with smtplib.SMTP_SSL(os.environ["SMTP_HOST"],port,timeout=15,context=ssl.create_default_context()) as server:
                    server.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"])
                    server.send_message(msg)
            else:
                with smtplib.SMTP(os.environ["SMTP_HOST"],port,timeout=15) as server:
                    server.starttls(context=ssl.create_default_context())
                    server.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"])
                    server.send_message(msg)
        except (OSError,smtplib.SMTPException) as exc:
            with get_connection() as db,db.cursor() as cur:
                cur.execute("""UPDATE public.email_notifications SET last_error=%s
                    WHERE id=%s AND teacher_id=%s AND status='pending'""",
                    (type(exc).__name__,notification_id,teacher_id))
            continue
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""UPDATE public.email_notifications
                SET status='sent',sent_at=now(),last_error=NULL
                WHERE id=%s AND teacher_id=%s AND status='pending'""",
                (notification_id,teacher_id))
        sent+=1
    return sent,None


def register(app,require,page,token,verifycsrf,E):
    @app.get("/notifications")
    def notifications(req:Request):
        teacher=require(req,"teacher")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT recipient,subject,status,created_at,last_error
                FROM public.email_notifications WHERE teacher_id=%s
                ORDER BY id DESC LIMIT 100""",(teacher["id"],))
            rows=cur.fetchall()
            cur.execute("""SELECT count(*) FROM public.email_notifications
                WHERE teacher_id=%s AND status='pending'""",(teacher["id"],))
            pending=cur.fetchone()[0]
        items="".join(f'<li>{E(created)} · {E(recipient)} · {E(subject)} — {E(status)} {E(error)}</li>'
                      for recipient,subject,status,created,error in rows)
        body=('<p><a href="/teacher">← Teacher dashboard</a></p>'
              '<article><h2>Email outbox</h2>'
              f'<p>{pending} pending. SMTP: {"configured" if smtp_configured() else "not configured"}.</p>'
              '<p>Sending is manual; messages are not delivered automatically.</p>'
              f'<form method="post" action="/notifications/send">{token(req)}'
              '<button>Send up to 20 pending emails</button></form></article>'
              f'<article><h2>Recent notifications</h2><ul>{items or "<li>No notifications yet.</li>"}</ul></article>')
        return page("Email Notifications",body)

    @app.post("/notifications/send")
    def send_notifications(req:Request,csrf:str=Form(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        sent,error=deliver_pending(teacher["id"])
        if error:
            raise HTTPException(503,error)
        return RedirectResponse("/notifications",status_code=303)
