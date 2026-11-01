from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from auth_service import (
    verify_student_access_token,
    get_student_activation_status,
)

router = APIRouter(prefix="/api/student-activation")


class ActivationCheckResponse(BaseModel):
    eligible: bool
    status: str

class ActivationCompleteRequest(BaseModel):
    password: str
    confirmation: str

    class Config:
        extra = "forbid"




def _get_student_activation_context(authorization: str | None):
    """Authenticate a student and retrieve activation status."""

    from supabase_auth.errors import AuthApiError, AuthError
    from psycopg import OperationalError, InterfaceError
    from psycopg import ProgrammingError

    from httpx import HTTPError

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    try:
        user_id = verify_student_access_token(token)
        status = get_student_activation_status(user_id)

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Student access required",
        )

    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication",
        )

    except AuthApiError as exc:
        if getattr(exc, "status", None) in (400, 401, 403):
            raise HTTPException(
                status_code=401,
                detail="Authentication verification failed",
            )

        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable",
        )

    except ProgrammingError:
        raise HTTPException(
            status_code=500,
            detail="Internal activation service error",
        )

    except (
        OperationalError,
        InterfaceError,
        AuthError,
        HTTPError,
        RuntimeError,
    ):
        raise HTTPException(
            status_code=503,
            detail="Activation service temporarily unavailable",
        )

    return user_id, status


@router.post("/check", response_model=ActivationCheckResponse)
def check_student_activation(
    authorization: str | None = Header(default=None),
):
    _, status = _get_student_activation_context(authorization)

    return ActivationCheckResponse(
        eligible=status == "pending",
        status=status,
    )


@router.post("/session-info")
def student_activation_session_info(
    authorization: str | None = Header(default=None),
):
    _, status = _get_student_activation_context(authorization)

    return {
        "authenticated": True,
        "role": "student",
        "activation_status": status,
    }


@router.post("/complete")
def complete_student_activation_endpoint(
    request: ActivationCompleteRequest,
    authorization: str | None = Header(default=None),
):
    from auth_service import complete_student_activation_for_user
    from student_activation_validation import (
        ActivationValidationError,
    )
    from psycopg import OperationalError, InterfaceError, ProgrammingError
    from supabase_auth.errors import AuthApiError, AuthError
    from httpx import HTTPError

    # Identity and student role are verified server-side.
    user_id, status = _get_student_activation_context(authorization)

    if status == "activated":
        return {"status": "already_activated"}

    # The service performs an atomic pending-only reservation.
    try:
        result = complete_student_activation_for_user(
            user_id,
            request.password,
            request.confirmation,
        )
    except ActivationValidationError:
        raise HTTPException(
            status_code=422,
            detail="Invalid activation password or confirmation",
        )
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Student activation not permitted",
        )
    except (OperationalError, InterfaceError, HTTPError, AuthError):
        raise HTTPException(
            status_code=503,
            detail="Activation requires administrative review",
        )
    except AuthApiError:
        raise HTTPException(
            status_code=503,
            detail="Activation requires administrative review",
        )
    except (ProgrammingError, RuntimeError):
        raise HTTPException(
            status_code=503,
            detail="Activation requires administrative review",
        )

    if result == "activated":
        return {"status": "activated"}

    if result == "already_activated":
        return {"status": "already_activated"}

    if result == "activation_processing":
        raise HTTPException(
            status_code=409,
            detail="Activation is already processing",
        )

    raise HTTPException(
        status_code=503,
        detail="Unexpected activation result",
    )
