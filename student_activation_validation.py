"""Validation for initial student password activation."""


class ActivationValidationError(ValueError):
    pass


def validate_activation_password(
    password: str,
    confirmation: str,
) -> None:
    if not isinstance(password, str):
        raise ActivationValidationError("Invalid password")

    if not isinstance(confirmation, str):
        raise ActivationValidationError("Invalid confirmation")

    if len(password) < 14:
        raise ActivationValidationError(
            "Password must contain at least 14 characters"
        )

    if len(password) > 128:
        raise ActivationValidationError(
            "Password is too long"
        )

    if password != confirmation:
        raise ActivationValidationError(
            "Passwords do not match"
        )
