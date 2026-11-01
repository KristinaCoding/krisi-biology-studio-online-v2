-- Student activation token storage
-- REVIEW ONLY: DO NOT EXECUTE YET

CREATE TABLE public.student_activation_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    student_id UUID NOT NULL
        REFERENCES public.student_profiles(id)
        ON DELETE CASCADE,

    token_hash TEXT NOT NULL UNIQUE,

    expires_at TIMESTAMPTZ NOT NULL,

    consumed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT activation_token_hash_not_empty
        CHECK (length(token_hash) > 0),

    CONSTRAINT activation_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX idx_student_activation_tokens_student
    ON public.student_activation_tokens(student_id);

CREATE INDEX idx_student_activation_tokens_expiry
    ON public.student_activation_tokens(expires_at);
