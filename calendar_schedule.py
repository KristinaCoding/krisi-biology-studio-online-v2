"""Monthly calendar for teacher sessions and student booking requests."""
import calendar
from datetime import date, datetime
from urllib.parse import urlencode
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse

def register(app, conn, require, page, token, verifycsrf, E):
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    def month_value(year, month):
        today = date.today()
        try:
            year, month = int(year or today.year), int(month or today.month)
            if not (2000 <= year <= 2100 and 1 <= month <= 12):
                raise ValueError()
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid calendar month")
        return year, month

    def calendar_table(year, month, entries):
        by_day = {}
        for when, label in entries:
            try:
                d = datetime.fromisoformat(when).date()
            except (TypeError, ValueError):
                continue
            if (d.year, d.month) == (year, month):
                by_day.setdefault(d.day, []).append(label)
        cells = ['<table class="calendar-grid"><thead><tr>' +
                 ''.join(f'<th>{d}</th>' for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")) +
                 '</tr></thead><tbody>']
        for week in calendar.monthcalendar(year, month):
            cells.append('<tr>')
            for day in week:
                if not day:
                    cells.append('<td></td>')
                else:
                    events = ''.join(f'<div class="calendar-entry">{E(label)}</div>' for label in by_day.get(day, []))
                    cells.append(f'<td><strong>{day}</strong>{events}</td>')
            cells.append('</tr>')
        cells.append('</tbody></table>')
        return ''.join(cells)

    def navigation(base, year, month):
        prev_y, prev_m = (year-1, 12) if month == 1 else (year, month-1)
        next_y, next_m = (year+1, 1) if month == 12 else (year, month+1)
        return (f'<p><a href="{base}?{urlencode({"year":prev_y,"month":prev_m})}">← Previous</a>'
                f' · <strong>{calendar.month_name[month]} {year}</strong> · '
                f'<a href="{base}?{urlencode({"year":next_y,"month":next_m})}">Next →</a></p>')

    @app.get("/calendar")
    def teacher_calendar(req: Request, year: int = None, month: int = None):
        require(req, "teacher")
        year, month = month_value(year, month)
        with conn() as c:
            students = c.execute("SELECT id,display FROM users WHERE role='student' ORDER BY display").fetchall()
            bookings = c.execute("""SELECT b.*, u.display FROM bookings b
                JOIN users u ON u.id=b.student_id ORDER BY b.requested""").fetchall()
            events = c.execute("""SELECT e.*, u.display FROM calendar_events e
                JOIN users u ON u.id=e.student_id ORDER BY e.starts_at""").fetchall()
        entries = [(b["requested"], f'{b["requested"][11:16]} · {b["display"]} · {b["status"]}') for b in bookings]
        entries += [(e["starts_at"], f'{e["starts_at"][11:16]} · {e["title"]} · {e["display"]}') for e in events]
        opts = ''.join(f'<option value="{s["id"]}">{E(s["display"])}</option>' for s in students)
        booking_rows = ''.join(
            f'<li>{E(b["display"])} — {E(b["requested"])} UTC ({E(b["status"])}) '
            f'<form method="post" action="/calendar/bookings/{b["id"]}" style="display:inline">{token(req)}'
            '<button name="decision" value="Approved">Approve</button> '
            '<button name="decision" value="Declined">Decline</button></form></li>'
            for b in bookings if b["status"] == "Requested"
        )
        event_rows = ''.join(
            f'<li>{E(e["title"])} — {E(e["display"])} — {E(e["starts_at"])} UTC '
            f'<form method="post" action="/calendar/events/{e["id"]}/delete" style="display:inline">{token(req)}'
            '<button>Delete</button></form></li>' for e in events
        )
        body = ('<p><a href="/teacher">← Teacher dashboard</a></p>'
                + navigation("/calendar", year, month)
                + '<article>' + calendar_table(year, month, entries) + '</article>'
                + '<article><h2>Schedule a lesson</h2>'
                + f'<form method="post" action="/calendar/events">{token(req)}'
                + f'<label>Student<select name="student_id" required>{opts}</select></label>'
                + '<label>Lesson title<input name="title" maxlength="150" required></label>'
                + '<label>Date and time (UTC)<input name="starts_at" type="datetime-local" required></label>'
                + '<label>Notes<textarea name="notes" maxlength="2000"></textarea></label>'
                + '<button>Schedule lesson</button></form></article>'
                + f'<article><h2>Pending bookings</h2><ul>{booking_rows or "<li>No pending requests.</li>"}</ul></article>'
                + f'<article><h2>Scheduled lessons</h2><ul>{event_rows or "<li>No scheduled lessons.</li>"}</ul></article>')
        return page("Teaching Calendar", body)

    @app.post("/calendar/events")
    def create_event(req: Request, student_id: int = Form(...), title: str = Form(...),
                     starts_at: str = Form(...), notes: str = Form(""), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        title, notes = title.strip(), notes.strip()
        if not title or len(title) > 150 or len(notes) > 2000:
            raise HTTPException(400, "Invalid lesson details")
        try:
            if datetime.fromisoformat(starts_at) <= datetime.now():
                raise ValueError()
        except ValueError:
            raise HTTPException(400, "Choose a future date and time")
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student_id,)).fetchone():
                raise HTTPException(400, "Invalid student")
            c.execute("INSERT INTO calendar_events(student_id,title,starts_at,notes) VALUES(?,?,?,?)",
                      (student_id, title, starts_at, notes))
        return RedirectResponse("/calendar", status_code=303)

    @app.post("/calendar/events/{event_id}/delete")
    def delete_event(req: Request, event_id: int, csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        with conn() as c:
            c.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
        return RedirectResponse("/calendar", status_code=303)

    @app.post("/calendar/bookings/{booking_id}")
    def decide_booking(req: Request, booking_id: int, decision: str = Form(...), csrf: str = Form(...)):
        require(req, "teacher")
        verifycsrf(req, csrf)
        if decision not in {"Approved", "Declined"}:
            raise HTTPException(400, "Invalid decision")
        with conn() as c:
            c.execute("UPDATE bookings SET status=? WHERE id=? AND status='Requested'", (decision, booking_id))
        return RedirectResponse("/calendar", status_code=303)

    @app.get("/my-calendar")
    def student_calendar(req: Request, year: int = None, month: int = None):
        u = require(req, "student")
        year, month = month_value(year, month)
        with conn() as c:
            bookings = c.execute("SELECT * FROM bookings WHERE student_id=? ORDER BY requested", (u["id"],)).fetchall()
            events = c.execute("SELECT * FROM calendar_events WHERE student_id=? ORDER BY starts_at", (u["id"],)).fetchall()
        entries = [(b["requested"], f'{b["requested"][11:16]} · Booking: {b["status"]}') for b in bookings]
        entries += [(e["starts_at"], f'{e["starts_at"][11:16]} · {e["title"]}') for e in events]
        body = ('<p><a href="/student">← Student dashboard</a></p>'
                + navigation("/my-calendar", year, month)
                + '<article>' + calendar_table(year, month, entries) + '</article>'
                + '<article><h2>My scheduled lessons</h2><ul>'
                + (''.join(f'<li>{E(e["title"])} — {E(e["starts_at"])} UTC</li>' for e in events) or '<li>No scheduled lessons.</li>')
                + '</ul></article><article><h2>My booking requests</h2><ul>'
                + (''.join(f'<li>{E(b["requested"])} UTC — {E(b["status"])}</li>' for b in bookings) or '<li>No booking requests.</li>')
                + '</ul></article>')
        return page("My Calendar", body)
