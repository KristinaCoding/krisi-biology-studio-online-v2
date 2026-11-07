"""Durable email outbox. Delivery is opt-in via SMTP environment settings."""
import os
import smtplib
import sqlite3
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse

def initialize(conn):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS email_notifications (
            id INTEGER PRIMARY KEY,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            last_error TEXT
        )""")

def queue(conn, recipient, subject, message):
    """Queue only; no network side effects during normal portal requests."""
    if not recipient or "@" not in recipient:
        return
    with conn() as c:
        c.execute("INSERT INTO email_notifications(recipient,subject,message) VALUES(?,?,?)",
                  (recipient.strip(), subject[:180], message[:10000]))

def notify_student(conn, student_id, subject, message):
    with conn() as c:
        student = c.execute("SELECT email FROM users WHERE id=? AND role='student'", (student_id,)).fetchone()
    if student:
        queue(conn, student["email"], subject, message)

def notify_teacher(conn, subject, message):
    with conn() as c:
        teachers = c.execute("SELECT email FROM users WHERE role='teacher'").fetchall()
    for teacher in teachers:
        queue(conn, teacher["email"], subject, message)

def smtp_configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"))

def deliver_pending(conn, limit=20):
    """Called explicitly by the teacher; SMTP uses TLS and is never enabled implicitly."""
    if not smtp_configured():
        return 0, "SMTP is not configured"
    host = os.environ["SMTP_HOST"]
    try:
        port = int(os.environ["SMTP_PORT"])
    except ValueError:
        return 0, "Invalid SMTP_PORT"
    if port not in (465, 587):
        return 0, "Use SMTP port 465 (SSL) or 587 (STARTTLS)"
    with conn() as c:
        rows = c.execute("SELECT * FROM email_notifications WHERE status='pending' ORDER BY id LIMIT ?", (limit,)).fetchall()
    sent = 0
    for item in rows:
        msg = EmailMessage()
        msg["From"] = os.environ["SMTP_FROM"]
        msg["To"] = item["recipient"]
        msg["Subject"] = item["subject"]
        msg.set_content(item["message"])
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as server:
                    server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.starttls(context=ssl.create_default_context())
                    server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                    server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            with conn() as c:
                c.execute("UPDATE email_notifications SET last_error=? WHERE id=?",
                          (type(exc).__name__, item["id"]))
            continue
        with conn() as c:
            c.execute("UPDATE email_notifications SET status='sent',sent_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=?",
                      (item["id"],))
        sent += 1
    return sent, None

def register(app, conn, require, page, token, verifycsrf, E):
    initialize(conn)

    @app.get("/notifications")
    def notifications(req: Request):
        require(req, "teacher")
        with conn() as c:
            rows = c.execute("SELECT id,recipient,subject,status,created_at,last_error FROM email_notifications ORDER BY id DESC LIMIT 100").fetchall()
            pending = c.execute("SELECT COUNT(*) FROM email_notifications WHERE status='pending'").fetchone()[0]
        items = "".join(
            f'<li>{E(r["created_at"])} · {E(r["recipient"])} · {E(r["subject"])} '
            f'— {E(r["status"])} {E(r["last_error"])}</li>' for r in rows
        )
        body = ('<p><a href="/teacher">← Teacher dashboard</a></p>'
                '<article><h2>Email outbox</h2>'
                f'<p>{pending} pending notifications. SMTP: {"configured" if smtp_configured() else "not configured"}.</p>'
                '<p>Messages are queued automatically. Sending requires SMTP configuration and manual confirmation.</p>'
                f'<form method="post" action="/notifications/send">{token(req)}'
                '<button>Send up to 20 pending emails</button></form></article>'
                f'<article><h2>Recent notifications</h2><ul>{items or "<li>No notifications yet.</li>"}</ul></article>')
        return page("Email Notifications", body)

    @app.post("/notifications/send")
    def send_notifications(req: Request, csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        sent, error = deliver_pending(conn)
        if error:
            raise HTTPException(503, error)
        return RedirectResponse("/notifications", status_code=303)
