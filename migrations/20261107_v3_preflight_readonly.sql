-- Read-only preflight: run before reviewing any v3 migrations.
-- Reports presence and type of the existing identity/relationship columns.
SELECT table_name,column_name,data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('teacher_profiles','student_profiles','teacher_students','bookings','quizzes','quiz_results')
ORDER BY table_name,ordinal_position;

SELECT conrelid::regclass AS table_name,conname,pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace='public'::regnamespace
  AND conrelid IN ('public.teacher_profiles'::regclass,
                   'public.student_profiles'::regclass,
                   'public.teacher_students'::regclass)
ORDER BY 1,2;

-- Read-only counts to record before and after deployment.
SELECT 'student_profiles' AS relation, count(*) AS records FROM public.student_profiles
UNION ALL SELECT 'teacher_profiles',count(*) FROM public.teacher_profiles
UNION ALL SELECT 'teacher_students',count(*) FROM public.teacher_students;
