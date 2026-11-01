
const assert = require("node:assert/strict");
const vm = require("node:vm");

const source = "\"use strict\";\n\nconst createRecoveryClient = globalThis.mockRecoveryClient;\n\n// Change to true only after final integration and recovery testing.\nconst ACTIVATION_ENABLED = false;\n\ndocument.addEventListener(\"DOMContentLoaded\", async () => {\n    const message = document.getElementById(\"activation-message\");\n    const form = document.getElementById(\"activation-form\");\n    const passwordInput = document.getElementById(\"new-password\");\n    const confirmationInput = document.getElementById(\"confirm-password\");\n\n    if (!message || !form || !passwordInput || !confirmationInput) {\n        return;\n    }\n\n    form.hidden = true;\n\n    const fragment = new URLSearchParams(\n        window.location.hash.replace(/^#/, \"\")\n    );\n\n    const isInvitation = fragment.get(\"type\") === \"invite\";\n    const accessToken = fragment.get(\"access_token\");\n    const refreshToken = fragment.get(\"refresh_token\");\n\n    // Remove invitation tokens from the address bar immediately.\n    window.history.replaceState(\n        null,\n        \"\",\n        window.location.pathname + window.location.search\n    );\n\n    if (!isInvitation || !accessToken || !refreshToken) {\n        message.textContent =\n            \"Open your valid student invitation email link.\";\n        return;\n    }\n\n    try {\n        const supabase = await createRecoveryClient();\n\n        const { data, error } = await supabase.auth.setSession({\n            access_token: accessToken,\n            refresh_token: refreshToken\n        });\n\n        if (error || !data?.session?.access_token) {\n            message.textContent =\n                \"Your invitation session could not be verified.\";\n            return;\n        }\n\n        const checkResponse = await fetch(\n            \"/api/student-activation/check\",\n            {\n                method: \"POST\",\n                headers: {\n                    \"Authorization\": `Bearer ${data.session.access_token}`\n                },\n                cache: \"no-store\"\n            }\n        );\n\n        if (!checkResponse.ok) {\n            message.textContent =\n                \"Student invitation verification failed.\";\n            return;\n        }\n\n        const checkResult = await checkResponse.json();\n\n        if (!checkResult.eligible || checkResult.status !== \"pending\") {\n            message.textContent =\n                \"This student account is not awaiting activation.\";\n            return;\n        }\n\n        if (!ACTIVATION_ENABLED) {\n            message.textContent =\n                \"Student identity verified. \" +\n                \"Password activation is awaiting final testing.\";\n            return;\n        }\n\n        form.hidden = false;\n        message.textContent =\n            \"Create a password to activate your student account.\";\n\n        let submitting = false;\n\n        form.addEventListener(\"submit\", async (event) => {\n            event.preventDefault();\n\n            if (submitting) return;\n\n            const password = passwordInput.value;\n            const confirmation = confirmationInput.value;\n\n            if (\n                password.length < 14 ||\n                password.length > 128 ||\n                password !== confirmation\n            ) {\n                message.textContent =\n                    \"Passwords must match and contain 14?128 characters.\";\n                return;\n            }\n\n            submitting = true;\n\n            const submitButton = form.querySelector(\n                'button[type=\"submit\"], input[type=\"submit\"]'\n            );\n\n            if (submitButton) submitButton.disabled = true;\n\n            try {\n                const { data: sessionData, error: sessionError } =\n                    await supabase.auth.getSession();\n\n                if (\n                    sessionError ||\n                    !sessionData?.session?.access_token\n                ) {\n                    throw new Error(\"Session unavailable\");\n                }\n\n                const response = await fetch(\n                    \"/api/student-activation/complete\",\n                    {\n                        method: \"POST\",\n                        headers: {\n                            \"Authorization\":\n                                `Bearer ${sessionData.session.access_token}`,\n                            \"Content-Type\": \"application/json\"\n                        },\n                        body: JSON.stringify({\n                            password,\n                            confirmation\n                        }),\n                        cache: \"no-store\"\n                    }\n                );\n\n                if (response.ok) {\n                    const result = await response.json();\n\n                    if (\n                        result.status === \"activated\" ||\n                        result.status === \"already_activated\"\n                    ) {\n                        form.hidden = true;\n                        message.textContent =\n                            \"Your student account is activated.\";\n                        return;\n                    }\n                }\n\n                if (response.status === 409) {\n                    form.hidden = true;\n                    message.textContent =\n                        \"Activation is being processed. \" +\n                        \"Please contact your teacher if this persists.\";\n                    return;\n                }\n\n                // A failed response can have an uncertain outcome.\n                // Never automatically retry a password update.\n                form.hidden = true;\n                message.textContent =\n                    \"Activation could not be confirmed. \" +\n                    \"Please contact your teacher.\";\n            } catch {\n                form.hidden = true;\n                message.textContent =\n                    \"Activation status is uncertain. \" +\n                    \"Please contact your teacher.\";\n            } finally {\n                passwordInput.value = \"\";\n                confirmationInput.value = \"\";\n                submitting = false;\n\n                if (submitButton) submitButton.disabled = false;\n            }\n        });\n    } catch {\n        message.textContent =\n            \"Unable to process your invitation securely.\";\n    }\n});\n";

async function runScenario(invitation) {
    const elements = {
        "activation-message": { textContent: "" },
        "activation-form": { hidden: false },
        "new-password": { value: "" },
        "confirm-password": { value: "" }
    };

    const calls = [];
    let ready;

    const readyPromise = new Promise(resolve => {
        ready = resolve;
    });

    const context = {
        URLSearchParams,
        Promise,
        console,
        document: {
            getElementById(id) {
                return elements[id] || null;
            },
            addEventListener(name, callback) {
                if (name === "DOMContentLoaded") {
                    Promise.resolve()
                        .then(callback)
                        .then(ready, ready);
                }
            }
        },
        window: {
            location: {
                hash: invitation
                    ? "#type=invite&access_token=test-access&refresh_token=test-refresh"
                    : "",
                pathname: "/accept-invite",
                search: ""
            },
            history: {
                replaceState(...args) {
                    calls.push(["history", ...args]);
                }
            }
        },
        mockRecoveryClient: async () => ({
            auth: {
                setSession: async () => ({
                    data: {
                        session: {
                            access_token: "mock-session"
                        }
                    },
                    error: null
                })
            }
        }),
        fetch: async (url) => {
            calls.push(["fetch", url]);
            return {
                ok: true,
                json: async () => ({
                    eligible: true,
                    status: "pending"
                })
            };
        }
    };

    vm.runInNewContext(source, context);
    await readyPromise;

    return { elements, calls };
}

(async () => {
    const noInvite = await runScenario(false);

    assert.equal(
        noInvite.elements["activation-form"].hidden,
        true
    );
    assert.match(
        noInvite.elements["activation-message"].textContent,
        /valid student invitation/
    );

    console.log("No invitation: PASS");

    const validInvite = await runScenario(true);

    assert.equal(
        validInvite.elements["activation-form"].hidden,
        true
    );
    assert.match(
        validInvite.elements["activation-message"].textContent,
        /awaiting final testing/
    );

    console.log("Pending invitation remains disabled: PASS");

    assert.ok(
        validInvite.calls.some(
            call => call[0] === "fetch" &&
            call[1] === "/api/student-activation/check"
        )
    );

    console.log("Eligibility API called: PASS");

    assert.ok(
        !validInvite.calls.some(
            call => call[0] === "fetch" &&
            call[1] === "/api/student-activation/complete"
        )
    );

    console.log("Password completion not called: PASS");

    assert.ok(
        validInvite.calls.some(
            call => call[0] === "history" &&
            call[3] === "/accept-invite"
        )
    );

    console.log("Invitation URL cleaned: PASS");

    console.log("TOTAL: 5/5 PASS");
})().catch(error => {
    console.error("MOCK TEST FAILED:", error.message);
    process.exitCode = 1;
});
