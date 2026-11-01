import os
from fastapi.responses import JSONResponse
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

router = APIRouter()


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(response: Response):
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "connect-src 'self' https://ydrexfodapmjamvhnsee.supabase.co; "
        "form-action 'self'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'"
    )

    template_path = (
        Path(__file__).resolve().parent
        / "templates"
        / "reset_password.html"
    )

    html_content = template_path.read_text(
        encoding="utf-8"
    )

    return HTMLResponse(
        content=html_content,
        headers=dict(response.headers),
    )


@router.get("/reset-password/status")
def recovery_status(response: Response):
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return {
        "service": "KRISI Biology Studio",
        "recovery_page": "available",
        "password_reset": "not_enabled_yet",
    }


@router.get("/auth/confirm")
def confirm_recovery_link(
    response: Response,
    type: str = "",
    token_hash: str = "",
):
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    if type != "recovery":
        raise HTTPException(
            status_code=400,
            detail="Invalid recovery request.",
            headers={
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )

    if not token_hash:
        raise HTTPException(
            status_code=400,
            detail="Recovery token is missing.",
            headers={
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )

    raise HTTPException(
        status_code=501,
        detail="Recovery verification is not enabled yet.",
        headers={
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        },
    )

@router.get("/auth/public-config")
def get_public_auth_config():
    supabase_url = os.getenv("SUPABASE_URL", "")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

    if not supabase_url or not publishable_key:
        return JSONResponse(
            status_code=503,
            content={"error": "Authentication configuration unavailable."},
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(
        content={
            "supabase_url": supabase_url,
            "supabase_publishable_key": publishable_key,
        },
        headers={"Cache-Control": "no-store"},
    )

from fastapi import Form
from fastapi.responses import RedirectResponse
from auth_service import request_password_recovery


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>KRISI Biology Studio — Forgot Password</title>
    </head>
    <body>
        <main>
            <h1>Forgot Password</h1>
            <p>Enter your account email to request a password reset link.</p>
            <form method="post" action="/forgot-password">
                <label for="email">Email address</label>
                <input id="email" name="email" type="email"
                       autocomplete="email" required>
                <button type="submit">Send Recovery Email</button>
            </form>
        </main>
    </body>
    </html>
    """)

@router.post("/forgot-password")
def send_forgot_password_email(email: str = Form(...)):
    try:
        request_password_recovery(email.strip())

    except Exception as exc:
        # Do not log email addresses, passwords, or recovery tokens.
        print(
            f"Password recovery request failed: {type(exc).__name__}",
            flush=True,
        )

    return HTMLResponse(
        "<h1>Check your email</h1>"
        "<p>If an account exists for that address, "
        "a password recovery email may arrive shortly.</p>"
    )
