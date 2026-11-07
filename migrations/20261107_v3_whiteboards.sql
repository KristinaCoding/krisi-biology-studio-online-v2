-- Additive migration; review live schema and backup before applying.
BEGIN;
CREATE TABLE IF NOT EXISTS public.whiteboards (
 student_id UUID PRIMARY KEY REFERENCES public.student_profiles(id),
 strokes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(strokes)='array'),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
