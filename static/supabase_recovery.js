
"use strict";

import { createRecoveryClient } from "./supabase_client.bundle.js";

document.addEventListener("DOMContentLoaded", async () => {
    const message = document.getElementById("recovery-message");
    const form = document.getElementById("reset-password-form");
    const password = document.getElementById("new-password");
    const confirmation = document.getElementById("confirm-password");
    const submit = form?.querySelector('button[type="submit"]');

    if (!message || !form || !password || !confirmation || !submit) {
        return;
    }

    let authorized = false;
    let processing = false;
    let supabase = null;

    function setEnabled(enabled) {
        password.disabled = !enabled;
        confirmation.disabled = !enabled;
        submit.disabled = !enabled;
    }

    setEnabled(false);

    const params = new URLSearchParams(
        window.location.hash.replace(/^#/, "")
    );

    const hasRecoveryCallback =
        params.get("type") === "recovery" &&
        !!params.get("access_token") &&
        !!params.get("refresh_token");

    if (!hasRecoveryCallback) {
        message.textContent =
            "Open a valid password recovery link from your email.";
        return;
    }

    // Supabase owns callback processing.
    // Do not manually enable the form based on URL tokens.

    try {
        supabase = await createRecoveryClient();

        message.textContent =
            "Checking Supabase recovery authorization...";

        supabase.auth.onAuthStateChange((event, session) => {
            if (event !== "PASSWORD_RECOVERY") {
                return;
            }

            if (!session?.access_token) {
                authorized = false;
                setEnabled(false);
                message.textContent =
                    "Recovery session unavailable. Request a new link.";
                return;
            }

            // Run verification outside the synchronous auth callback.
            setTimeout(async () => {
                try {
                    const { data, error } =
                        await supabase.auth.getUser(
                            session.access_token
                        );

                    if (error || !data?.user) {
                        throw new Error("User verification failed");
                    }

                    authorized = true;
                    setEnabled(true);

                    message.textContent =
                        "Recovery verified. Enter your new password.";

                } catch {
                    authorized = false;
                    setEnabled(false);

                    message.textContent =
                        "Recovery verification failed. Request a new link.";
                }
            }, 0);
        });

        const { error: initializationError } =
            await supabase.auth.initialize();

        if (initializationError) {
            authorized = false;
            setEnabled(false);

            console.error(
                "Supabase recovery initialization:",
                initializationError.name || "Unknown error"
            );

            message.textContent =
                "Recovery link verification failed. Request a new link.";
        }

    } catch (error) {
        authorized = false;
        setEnabled(false);

        console.error(
            "Recovery initialization failed:",
            error?.name || "Unknown error"
        );

        message.textContent =
            "Authentication service unavailable. Please try again.";
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (!authorized || !supabase || processing) {
            return;
        }

        if (password.value.length < 12) {
            message.textContent =
                "Password must contain at least 12 characters.";
            return;
        }

        if (password.value !== confirmation.value) {
            message.textContent = "Passwords do not match.";
            return;
        }

        processing = true;
        setEnabled(false);
        message.textContent = "Updating password...";

        try {
            const { error } = await supabase.auth.updateUser({
                password: password.value
            });

            if (error) {
                throw error;
            }

            authorized = false;
            password.value = "";
            confirmation.value = "";

            await supabase.auth.signOut();

            message.textContent =
                "Password updated successfully. You can now sign in.";

        } catch {
            authorized = false;
            message.textContent =
                "Password update failed. Please request a new recovery link.";
        } finally {
            processing = false;
            setEnabled(false);
        }
    });
});
