import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Supabase Authentication settings are missing."
        )

    return create_client(url, key)

from uuid import UUID

from database import get_connection


def get_user_role(user_id: str) -> str | None:
    """Look up a verified user's role in PostgreSQL."""
    UUID(user_id)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 'teacher'
                FROM public.teacher_profiles
                WHERE id = %s

                UNION ALL

                SELECT 'student'
                FROM public.student_profiles
                WHERE id = %s
                """,
                (user_id, user_id),
            )

            roles = [row[0] for row in cursor.fetchall()]

    if len(roles) != 1:
        return None

    return roles[0]

def verify_recovery_token(token_hash: str):
    """Verify a recovery token using an isolated client."""
    if not token_hash:
        raise ValueError("Recovery token is required.")

    client = create_recovery_client()

    return client.auth.verify_otp({
        "type": "recovery",
        "token_hash": token_hash,
    })

from supabase_auth.errors import AuthApiError


def check_recovery_token(token_hash: str) -> bool:

    """
    Test helper for invalid tokens only.

    Do not use with real recovery links or in FastAPI routes.
    Successful OTP verification creates authentication credentials
    that must be handled by the complete recovery flow.
    """

    if not token_hash:
        return False

    try:
        verify_recovery_token(token_hash)
        return True

    except AuthApiError:
        return False



from supabase import ClientOptions


def create_recovery_client() -> Client:
    """Create a client with no persistent auth session."""
    load_dotenv()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Supabase Authentication settings are missing."
        )

    options = ClientOptions(
        persist_session=False,
        auto_refresh_token=False,
    )

    return create_client(url, key, options=options)


def request_password_recovery(email: str):
    """Send a password recovery email through Supabase Auth."""
    import os

    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    redirect_url = os.environ.get(
        "PASSWORD_RECOVERY_REDIRECT_URL",
        "http://127.0.0.1:8000/reset-password"
    )

    client = create_client(url, key)

    return client.auth.reset_password_email(
        email,
        options={"redirect_to": redirect_url}
    )

def authenticate_portal_user(email: str, password: str):
    """Authenticate through Supabase and resolve the PostgreSQL role."""
    from supabase_auth.errors import AuthApiError

    client = create_recovery_client()

    try:
        response = client.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": password,
        })
    except AuthApiError:
        return None

    authenticated_user = response.user

    if authenticated_user is None:
        return None

    user_id = str(authenticated_user.id)
    role = get_user_role(user_id)

    if role not in ("teacher", "student"):
        return None

    if role == "student":
        try:
            activation_status = get_student_activation_status(user_id)
        except (PermissionError, RuntimeError):
            return None

        if activation_status != "activated":
            return None

    return {
        "supabase_user_id": user_id,
        "email": authenticated_user.email,
        "role": role,
    }


def create_admin_client():
    """Create a server-only Supabase client for administrative operations."""
    import os
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    secret = os.environ["SUPABASE_SECRET_KEY"]

    return create_client(url, secret)


def invite_student_by_email(email: str, redirect_url: str):
    """Invite a student through the server-side Supabase Admin API."""
    from urllib.parse import urlparse

    email = email.strip().lower()
    redirect_url = redirect_url.strip()

    if not email or "@" not in email:
        raise ValueError("A valid student email is required")

    parsed = urlparse(redirect_url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("A valid invitation redirect URL is required")

    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
    ):
        raise ValueError("Non-local invitation redirects must use HTTPS")

    client = create_admin_client()

    return client.auth.admin.invite_user_by_email(
        email,
        options={"redirect_to": redirect_url},
    )


def register_invited_student(user_id: str, display_name: str):
    """Register an invited Supabase Auth user as a student."""
    from uuid import UUID
    from database import get_connection

    validated_id = str(UUID(user_id))
    display_name = display_name.strip()

    if not display_name:
        raise ValueError("Student display name is required")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.student_profiles (id, display_name)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """,
                (validated_id, display_name),
            )
            inserted = cursor.fetchone()

    return inserted is not None


def verify_student_invitation(token_hash: str):
    """Verify a Supabase student invitation token."""
    from supabase_auth.types import VerifyTokenHashParams

    if not token_hash or len(token_hash) > 4096:
        raise ValueError("Invalid invitation token")

    client = create_recovery_client()

    response = client.auth.verify_otp(
        VerifyTokenHashParams(
            token_hash=token_hash,
            type="invite",
        )
    )

    if not response.user or not response.session:
        raise ValueError("Invitation verification failed")

    if get_user_role(str(response.user.id)) != "student":
        raise PermissionError("Invitation is not linked to a student profile")

    return response


def activate_invited_student(token_hash: str, new_password: str):
    """Verify a student invitation and set the student's password."""
    if len(new_password) < 14:
        raise ValueError("Password must contain at least 14 characters")

    response = verify_student_invitation(token_hash)

    session = response.session

    if not session or not session.access_token or not session.refresh_token:
        raise ValueError("A verified invitation session is required")

    client = create_recovery_client()

    client.auth.set_session(
        session.access_token,
        session.refresh_token,
    )

    updated = client.auth.update_user({
        "password": new_password,
    })

    if not updated.user:
        raise RuntimeError("Student password update failed")

    return str(updated.user.id)


def begin_student_activation(token_hash: str):
    """Verify an invitation and create a temporary activation record."""
    from student_activation import create_activation_record

    response = verify_student_invitation(token_hash)

    session = response.session
    invited_user = response.user

    if not session or not invited_user:
        raise ValueError("A verified invitation session is required")

    if not session.access_token or not session.refresh_token:
        raise ValueError("Supabase session tokens are missing")

    return create_activation_record(
        user_id=str(invited_user.id),
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


def complete_student_activation(activation_id: str, new_password: str):
    """Set a student password using a verified activation session."""
    from student_activation import consume_activation_record

    if len(new_password) < 14:
        raise ValueError("Password must contain at least 14 characters")

    record = consume_activation_record(activation_id)

    if record is None:
        raise ValueError("Activation session expired or already used")

    client = create_recovery_client()

    client.auth.set_session(
        record["access_token"],
        record["refresh_token"],
    )

    current_user = client.auth.get_user()

    if not current_user.user:
        raise PermissionError("Verified student session is unavailable")

    if str(current_user.user.id) != record["user_id"]:
        raise PermissionError("Activation account mismatch")

    if get_user_role(record["user_id"]) != "student":
        raise PermissionError("Account is not registered as a student")

    updated = client.auth.update_user({
        "password": new_password,
    })

    if not updated.user or str(updated.user.id) != record["user_id"]:
        raise RuntimeError("Student password update failed")

    return record["user_id"]


def verify_student_access_token(access_token: str) -> str:
    """Verify a Supabase access token and its student role."""
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Missing access token")

    client = create_recovery_client()
    response = client.auth.get_user(access_token)

    user = getattr(response, "user", None)
    if user is None:
        raise PermissionError("Invalid authentication token")

    user_id = str(user.id)

    if get_user_role(user_id) != "student":
        raise PermissionError("Student access required")

    return user_id


def mark_student_activated(user_id: str) -> bool:
    """Atomically mark a student as activated once."""
    import uuid
    from database import get_connection

    validated_id = str(uuid.UUID(user_id))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.student_profiles
                SET activated_at = NOW()
                WHERE id = %s
                  AND activated_at IS NULL
                RETURNING id
                """,
                (validated_id,),
            )

            updated = cursor.fetchone() is not None

        connection.commit()

    return updated


def get_student_activation_status(user_id: str) -> str:
    from uuid import UUID

    validated_id = str(UUID(user_id))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT activation_status
                FROM public.student_profiles
                WHERE id = %s
                """,
                (validated_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise PermissionError("Student profile not found")

    status = row[0]

    if status not in ("pending", "processing", "activated"):
        raise RuntimeError("Unexpected student activation status")

    return status

def complete_student_activation_for_user(
    user_id: str,
    password: str,
    confirmation: str,
) -> str:
    from uuid import UUID, uuid4
    from student_activation_validation import validate_activation_password

    validated_id = str(UUID(user_id))
    validate_activation_password(password, confirmation)

    attempt_id = str(uuid4())

    # Phase 1: Reserve activation and commit before contacting Supabase.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.student_profiles
                SET activation_status = 'processing',
                    activation_started_at = NOW(),
                    activation_attempt_id = %s
                WHERE id = %s
                  AND activation_status = 'pending'
                  AND activated_at IS NULL
                RETURNING id
                """,
                (attempt_id, validated_id),
            )

            reserved = cursor.fetchone()

            if reserved is None:
                cursor.execute(
                    """
                    SELECT activation_status
                    FROM public.student_profiles
                    WHERE id = %s
                    """,
                    (validated_id,),
                )
                row = cursor.fetchone()

                if row is None:
                    raise PermissionError("Student profile not found")

                if row[0] == "activated":
                    return "already_activated"

                if row[0] == "processing":
                    return "activation_processing"

                raise RuntimeError("Unexpected activation state")

    # Phase 2: External operation.
    # An uncertain result must NOT automatically reset processing.
    client = create_admin_client()
    updated = client.auth.admin.update_user_by_id(
        validated_id,
        {"password": password},
    )

    updated_user = getattr(updated, "user", None)

    if (
        updated_user is None
        or str(getattr(updated_user, "id", "")) != validated_id
    ):
        raise RuntimeError(
            "Password update outcome requires administrative review"
        )

    # Phase 3: Finalize only the reserved attempt.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.student_profiles
                SET activation_status = 'activated',
                    activated_at = NOW(),
                    activation_started_at = NULL,
                    activation_attempt_id = NULL
                WHERE id = %s
                  AND activation_status = 'processing'
                  AND activation_attempt_id = %s
                  AND activated_at IS NULL
                RETURNING id
                """,
                (validated_id, attempt_id),
            )

            if cursor.fetchone() is None:
                raise RuntimeError(
                    "Activation finalization requires administrative review"
                )

    return "activated"
