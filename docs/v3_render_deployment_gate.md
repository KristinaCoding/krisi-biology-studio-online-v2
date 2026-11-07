# Biology Studio v3 — PostgreSQL deployment gate

**Status: NOT READY TO DEPLOY.** This branch is a staging area. The v3 modules copied from main still use SQLite and are intentionally not registered in the deployed PostgreSQL portal.

## Existing application contract
- Render service: `krisi-biology-portal`; deployment branch: `postgresql-migration`.
- Portal authenticates via Supabase and uses UUID identities.
- Teacher/student membership is defined by `public.teacher_students`.
- Core lessons and booking records are PostgreSQL-backed.
- No data reset, table replacement, or automatic migration on application startup.

## Required integration work
- [ ] Replace SQLite queries and integer `users.id` references in each staged v3 module with PostgreSQL queries and UUID student IDs.
- [ ] Enforce teacher-to-student membership for all teacher-created and teacher-read objects, not only UI lists.
- [ ] Prepare additive, reviewed PostgreSQL migrations for each module. Verify existing schema and constraints first.
- [ ] Adapt dashboard and routes in `portal.py` without replacing the deployed Supabase authentication and session model.
- [ ] Replace local private file storage with persistent private object storage; verify authorization on downloads.
- [ ] Resolve student invitation/activation flow and email notifications before enabling them.
- [ ] Test teacher/student permissions, CSRF, input validation, migrations, and rollback.
- [ ] Back up and verify existing student, lesson, and booking data before any SQL is executed.
- [ ] Apply approved migrations only after backup; verify existing record counts and foreign keys.
- [ ] Deploy only after tests pass; monitor logs and smoke-test teacher/student sign-in.

## Staged assets
- Dashboard CSS and quiz/whiteboard JavaScript have been copied from v3.
- Nine v3 Python modules are copied for conversion; **they are not PostgreSQL-ready**.
- `migrations/20261107_v3_biology_activities.sql` is a draft and **must not be run without schema review**.

## Rollback
Keep `postgresql-migration` untouched until release. Take a restorable database backup before SQL changes. Rolling back Render code does not roll back schema or recover data; use additive migrations and a verified backup.
