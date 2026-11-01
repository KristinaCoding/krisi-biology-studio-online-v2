"use strict";

import { createRecoveryClient } from "./supabase_client.bundle.js";

// Change to true only after final integration and recovery testing.
const ACTIVATION_ENABLED = false;

document.addEventListener("DOMContentLoaded", async () => {
    const message = document.getElementById("activation-message");
    const form = document.getElementById("activation-form");
    const passwordInput = document.getElementById("new-password");
    const confirmationInput = document.getElementById("confirm-password");

    if (!message || !form || !passwordInput || !confirmationInput) {
        return;
    }

    form.hidden = true;

    const fragment = new URLSearchParams(
        window.location.hash.replace(/^#/, "")
    );

    const isInvitation = fragment.get("type") === "invite";
    const accessToken = fragment.get("access_token");
    const refreshToken = fragment.get("refresh_token");

    // Remove invitation tokens from the address bar immediately.
    window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
    );

    if (!isInvitation || !accessToken || !refreshToken) {
        message.textContent =
            "Open your valid student invitation email link.";
        return;
    }

    try {
        const supabase = await createRecoveryClient();

        const { data, error } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: refreshToken
        });

        if (error || !data?.session?.access_token) {
            message.textContent =
                "Your invitation session could not be verified.";
            return;
        }

        const checkResponse = await fetch(
            "/api/student-activation/check",
            {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${data.session.access_token}`
                },
                cache: "no-store"
            }
        );

        if (!checkResponse.ok) {
            message.textContent =
                "Student invitation verification failed.";
            return;
        }

        const checkResult = await checkResponse.json();

        if (!checkResult.eligible || checkResult.status !== "pending") {
            message.textContent =
                "This student account is not awaiting activation.";
            return;
        }

        if (!ACTIVATION_ENABLED) {
            message.textContent =
                "Student identity verified. " +
                "Password activation is awaiting final testing.";
            return;
        }

        form.hidden = false;
        message.textContent =
            "Create a password to activate your student account.";

        let submitting = false;

        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            if (submitting) return;

            const password = passwordInput.value;
            const confirmation = confirmationInput.value;

            if (
                password.length < 14 ||
                password.length > 128 ||
                password !== confirmation
            ) {
                message.textContent =
                    "Passwords must match and contain 14?128 characters.";
                return;
            }

            submitting = true;

            const submitButton = form.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (submitButton) submitButton.disabled = true;

            try {
                const { data: sessionData, error: sessionError } =
                    await supabase.auth.getSession();

                if (
                    sessionError ||
                    !sessionData?.session?.access_token
                ) {
                    throw new Error("Session unavailable");
                }

                const response = await fetch(
                    "/api/student-activation/complete",
                    {
                        method: "POST",
                        headers: {
                            "Authorization":
                                `Bearer ${sessionData.session.access_token}`,
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            password,
                            confirmation
                        }),
                        cache: "no-store"
                    }
                );

                if (response.ok) {
                    const result = await response.json();

                    if (
                        result.status === "activated" ||
                        result.status === "already_activated"
                    ) {
                        form.hidden = true;
                        message.textContent =
                            "Your student account is activated.";
                        return;
                    }
                }

                if (response.status === 409) {
                    form.hidden = true;
                    message.textContent =
                        "Activation is being processed. " +
                        "Please contact your teacher if this persists.";
                    return;
                }

                // A failed response can have an uncertain outcome.
                // Never automatically retry a password update.
                form.hidden = true;
                message.textContent =
                    "Activation could not be confirmed. " +
                    "Please contact your teacher.";
            } catch {
                form.hidden = true;
                message.textContent =
                    "Activation status is uncertain. " +
                    "Please contact your teacher.";
            } finally {
                passwordInput.value = "";
                confirmationInput.value = "";
                submitting = false;

                if (submitButton) submitButton.disabled = false;
            }
        });
    } catch {
        message.textContent =
            "Unable to process your invitation securely.";
    }
});
