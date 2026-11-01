
"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("reset-password-form");
    const message = document.getElementById("recovery-message");

    if (!form || !message) {
        return;
    }

    // Keep password recovery disabled during development.
    const passwordFields = form.querySelectorAll(
        'input[type="password"]'
    );
    const submitButton = form.querySelector(
        'button[type="submit"]'
    );

    passwordFields.forEach((field) => {
        field.disabled = true;
    });

    if (submitButton) {
        submitButton.disabled = true;
    }



const fragment = window.location.hash;
const fragmentParams = new URLSearchParams(
    fragment.startsWith("#") ? fragment.slice(1) : ""
);

const recoveryError = fragmentParams.has("error");

const hasRecoveryTokens =
    fragmentParams.has("access_token") &&
    fragmentParams.has("refresh_token") &&
    fragmentParams.get("type") === "recovery";


if (recoveryError) {
    // Do not display raw URL values or tokens.
    window.history.replaceState(
        null,
        "",
        window.location.pathname
    );

    message.textContent =
        "The recovery link could not be verified. Please request a new link.";


} else if (hasRecoveryTokens) {
    // The Supabase recovery module owns token processing
    // and URL cleanup. This script must not remove tokens.

    message.textContent =
        "Recovery link detected. Secure verification is not enabled yet.";

} else if (fragment) {
    window.history.replaceState(
        null,
        "",
        window.location.pathname
    );

    message.textContent =
        "The recovery link is incomplete or unsupported.";

} else {
    // The Supabase recovery module manages
    // the authentication status message.
}

form.addEventListener("submit", (event) => {
    event.preventDefault();
});

});


