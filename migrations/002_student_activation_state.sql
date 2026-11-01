-- KRISI Biology Studio
-- Student activation state machine
-- REVIEW ONLY: DO NOT EXECUTE YET

BEGIN;

ALTER TABLE public.student_profiles
ADD COLUMN activation_status TEXT NOT NULL DEFAULT 'pending',
ADD COLUMN activation_started_at TIMESTAMPTZ,
ADD COLUMN activation_attempt_id UUID;

UPDATE public.student_profiles
SET activation_status = CASE
    WHEN activated_at IS NOT NULL THEN 'activated'
    ELSE 'pending'
END;

ALTER TABLE public.student_profiles
ADD CONSTRAINT student_activation_status_valid
CHECK (
    activation_status IN (
        'pending',
        'processing',
        'activated'
    )
);

ALTER TABLE public.student_profiles
ADD CONSTRAINT student_activation_state_consistent
CHECK (
    (
        activation_status = 'pending'
        AND activated_at IS NULL
        AND activation_started_at IS NULL
        AND activation_attempt_id IS NULL
    )
    OR
    (
        activation_status = 'processing'
        AND activated_at IS NULL
        AND activation_started_at IS NOT NULL
        AND activation_attempt_id IS NOT NULL
    )
    OR
    (
        activation_status = 'activated'
        AND activated_at IS NOT NULL
        AND activation_started_at IS NULL
        AND activation_attempt_id IS NULL
    )
);

CREATE INDEX idx_student_activation_processing
ON public.student_profiles (activation_started_at)
WHERE activation_status = 'processing';

COMMIT;
