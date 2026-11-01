# krisi.site Biology Student Portal v1.0 — LOCAL DEVELOPMENT PREVIEW

This is a **separate FastAPI web app**, not a drop-in replacement for your Streamlit `app.py`. Your current v0.9 Streamlit Studio stays unchanged. The two databases **do not sync**. Do **not** deploy this preview publicly or enter real student personal information.

## Local Windows setup
1. Back up your entire existing `krisi_studio` folder.
2. Extract this ZIP into a NEW folder such as `krisi_student_portal`. Do not overwrite your existing `app.py` or `studio.db`.
3. In a PowerShell terminal in the new folder, activate your Python environment and run:
   `pip install -r requirements.txt`
4. Set a random secret in that terminal:
   `$env:PORTAL_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")`
5. Run `python create_teacher.py` and create your teacher account.
6. Run `uvicorn portal:app --host 127.0.0.1 --port 8000`
7. Open `http://127.0.0.1:8000` and sign in.

## Test workflow
- Sign in as teacher and create a **fictional** student with a unique email and strong password.
- Assign that student a lesson and a provider-hosted HTTPS video meeting URL.
- Assign a multiple-choice or true/false quiz using the JSON template.
- Sign out, sign in as the student, view the lesson, submit the quiz, request a booking.
- Sign in as teacher and inspect the saved quiz result and booking request.

## What works in this local preview
- Password hashing using PBKDF2, session cookies, basic teacher/student role checks, per-student query filtering, CSRF checks on application forms.
- Teacher creates student accounts for **local testing only**.
- Teacher assigns lessons and meeting URLs.
- Student submits a quiz once; score is stored in portal.db and visible to teacher.
- Student requests a booking; teacher approves/declines it.

## What is NOT implemented / production blockers
- **Not integrated two-way video**: lessons open an external provider's meeting URL. Live video depends on that provider.
- **Not a production-secure portal**: needs independent security review, HTTPS, secure hosting, password resets, invitation-based enrollment, email verification, login rate limiting, audit logs, database backup/encryption, privacy policy and retention controls, and safeguarding procedures for minors.
- **No automatic reminders**: booking status changes are displayed in portal only; no email or SMS is sent.
- **No Streamlit sync**: the teacher's existing local Studio and portal have separate data stores. Do not copy `studio.db` into the portal.
- **No student-facing answer explanations** and no secure online exam controls.
- The `datetime-local` booking input is treated as local machine time, not converted between time zones.
- Student creation currently takes place directly in the teacher dashboard; temporary passwords must not be used with real students.
- No shared whiteboard or synchronized lesson materials yet.

Before public deployment to krisi.site, plan a hosted backend, restricted student onboarding, provider-hosted classroom integration, and a secure data synchronization strategy. Use fictional data for testing.


## Dark Academia v1.1
Visual redesign of the FastAPI student portal. All existing routes, login, teacher/student workflows, quiz grading, and bookings are retained. Styling lives in `dark_academia.css`. The local SQLite database is not included; back up `portal.db` before transferring it from an older version. Requires the existing `PORTAL_SECRET` environment variable. See original setup instructions above.
