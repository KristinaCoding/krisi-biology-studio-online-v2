"""PostgreSQL teacher/student lesson calendar, using existing bookings."""
import calendar
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from uuid import UUID
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from database import get_connection


def register(app, require, page, token, verifycsrf, E):
    def month_value(year,month):
        today=date.today()
        y,m=year or today.year,month or today.month
        if not 2000<=y<=2100 or not 1<=m<=12:
            raise HTTPException(400,"Invalid calendar month")
        return y,m

    def navigation(base,y,m):
        py,pm=(y-1,12) if m==1 else (y,m-1)
        ny,nm=(y+1,1) if m==12 else (y,m+1)
        return (f'<p><a href="{base}?{urlencode({"year":py,"month":pm})}">← Previous</a>'
                f' · {calendar.month_name[m]} {y} · '
                f'<a href="{base}?{urlencode({"year":ny,"month":nm})}">Next →</a></p>')

    def calendar_table(y,m,entries):
        by_day={}
        for when,label in entries:
            d=when.date() if isinstance(when,datetime) else datetime.fromisoformat(str(when)).date()
            if (d.year,d.month)==(y,m):
                by_day.setdefault(d.day,[]).append(label)
        rows=[]
        for week in calendar.monthcalendar(y,m):
            cells=[]
            for day in week:
                labels="".join(f'<div class="calendar-entry">{E(x)}</div>' for x in by_day.get(day,[]))
                cells.append(f'<td><strong>{day}</strong>{labels}</td>' if day else '<td></td>')
            rows.append('<tr>'+''.join(cells)+'</tr>')
        return ('<table class="calendar-grid"><thead><tr>'
                +''.join(f'<th>{d}</th>' for d in ("Mon","Tue","Wed","Thu","Fri","Sat","Sun"))
                +'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>')

    @app.get("/calendar")
    def teacher_calendar(req:Request,year:int=None,month:int=None):
        teacher=require(req,"teacher")
        y,m=month_value(year,month)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""",(teacher["id"],))
            students=cur.fetchall()
            cur.execute("""SELECT b.id,b.requested_at,b.status,s.display_name FROM public.bookings b
                JOIN public.teacher_students ts ON ts.teacher_id=b.teacher_id AND ts.student_id=b.student_id
                JOIN public.student_profiles s ON s.id=b.student_id
                WHERE b.teacher_id=%s ORDER BY b.requested_at""",(teacher["id"],))
            bookings=cur.fetchall()
            cur.execute("""SELECT e.id,e.title,e.starts_at,s.display_name FROM public.calendar_events e
                JOIN public.teacher_students ts ON ts.teacher_id=e.teacher_id AND ts.student_id=e.student_id
                JOIN public.student_profiles s ON s.id=e.student_id
                WHERE e.teacher_id=%s ORDER BY e.starts_at""",(teacher["id"],))
            events=cur.fetchall()
        entries=[(when,f'{when:%H:%M} · {name} · {status}') for _,when,status,name in bookings]
        entries += [(when,f'{when:%H:%M} · {title} · {name}') for _,title,when,name in events]
        options="".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        pending="".join(f'<li>{E(name)} — {E(when)} UTC ({E(status)})</li>'
                        for _,when,status,name in bookings if status=="Requested")
        scheduled="".join(f'<li>{E(title)} — {E(name)} — {E(when)} UTC '
                          f'<form method="post" action="/calendar/events/{eid}/delete" style="display:inline">'
                          f'{token(req)}<button>Delete</button></form></li>'
                          for eid,title,when,name in events)
        body=('<p><a href="/teacher">← Teacher dashboard</a></p>'+navigation("/calendar",y,m)
              +'<article>'+calendar_table(y,m,entries)+'</article>'
              +'<article><h2>Schedule a lesson</h2>'
              +f'<form method="post" action="/calendar/events">{token(req)}'
              +f'<label>Student<select name="student_id" required>{options}</select></label>'
              +'<label>Lesson title<input name="title" maxlength="150" required></label>'
              +'<label>Date and time (UTC)<input name="starts_at" type="datetime-local" required></label>'
              +'<label>Notes<textarea name="notes" maxlength="2000"></textarea></label>'
              +'<button>Schedule lesson</button></form></article>'
              +f'<article><h2>Pending bookings</h2><ul>{pending or "<li>No pending requests.</li>"}</ul>'
              +'<p>Approve or decline booking requests from the teacher dashboard.</p></article>'
              +f'<article><h2>Scheduled lessons</h2><ul>{scheduled or "<li>No scheduled lessons.</li>"}</ul></article>')
        return page("Teaching Calendar",body)

    @app.post("/calendar/events")
    def create_event(req:Request,student_id:str=Form(...),title:str=Form(...),
                     starts_at:str=Form(...),notes:str=Form(""),csrf:str=Form(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        try:
            sid=str(UUID(student_id))
            when=datetime.strptime(starts_at,"%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400,"Invalid student or time")
        title,notes=title.strip(),notes.strip()
        if not 1<=len(title)<=150 or len(notes)>2000 or when<=datetime.now(timezone.utc):
            raise HTTPException(400,"Invalid lesson details or time")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""INSERT INTO public.calendar_events
                (teacher_id,student_id,title,starts_at,notes)
                SELECT ts.teacher_id,ts.student_id,%s,%s,%s FROM public.teacher_students ts
                WHERE ts.teacher_id=%s AND ts.student_id=%s RETURNING id""",
                (title,when,notes,teacher["id"],sid))
            if not cur.fetchone():
                raise HTTPException(403,"Student not assigned to this teacher")
        return RedirectResponse("/calendar",status_code=303)

    @app.post("/calendar/events/{event_id}/delete")
    def delete_event(req:Request,event_id:int,csrf:str=Form(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("DELETE FROM public.calendar_events WHERE id=%s AND teacher_id=%s RETURNING id",
                        (event_id,teacher["id"]))
            if not cur.fetchone():
                raise HTTPException(404,"Lesson not found")
        return RedirectResponse("/calendar",status_code=303)

    @app.get("/my-calendar")
    def student_calendar(req:Request,year:int=None,month:int=None):
        student=require(req,"student")
        y,m=month_value(year,month)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT b.requested_at,b.status FROM public.bookings b
                JOIN public.teacher_students ts ON ts.teacher_id=b.teacher_id AND ts.student_id=b.student_id
                WHERE b.student_id=%s ORDER BY b.requested_at""",(student["id"],))
            bookings=cur.fetchall()
            cur.execute("""SELECT e.title,e.starts_at FROM public.calendar_events e
                JOIN public.teacher_students ts ON ts.teacher_id=e.teacher_id AND ts.student_id=e.student_id
                WHERE e.student_id=%s ORDER BY e.starts_at""",(student["id"],))
            events=cur.fetchall()
        entries=[(when,f'{when:%H:%M} · Booking: {status}') for when,status in bookings]
        entries += [(when,f'{when:%H:%M} · {title}') for title,when in events]
        listing="".join(f'<li>{E(title)} — {E(when)} UTC</li>' for title,when in events)
        requests="".join(f'<li>{E(when)} UTC — {E(status)}</li>' for when,status in bookings)
        return page("My Calendar",'<p><a href="/student">← Student dashboard</a></p>'
                    +navigation("/my-calendar",y,m)
                    +'<article>'+calendar_table(y,m,entries)+'</article>'
                    +f'<article><h2>My scheduled lessons</h2><ul>{listing or "<li>No scheduled lessons.</li>"}</ul></article>'
                    +f'<article><h2>My booking requests</h2><ul>{requests or "<li>No booking requests.</li>"}</ul></article>')
