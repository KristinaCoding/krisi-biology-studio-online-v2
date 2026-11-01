
const assert = require("node:assert/strict");
const vm = require("node:vm");

const source = "\"use strict\";\n\nconst createRecoveryClient = globalThis.mockRecoveryClient;\n\n// Change to true only after final integration and recovery testing.\nconst ACTIVATION_ENABLED = true;\n\ndocument.addEventListener(\"DOMContentLoaded\", async () => {\n    const message = document.getElementById(\"activation-message\");\n    const form = document.getElementById(\"activation-form\");\n    const passwordInput = document.getElementById(\"new-password\");\n    const confirmationInput = document.getElementById(\"confirm-password\");\n\n    if (!message || !form || !passwordInput || !confirmationInput) {\n        return;\n    }\n\n    form.hidden = true;\n\n    const fragment = new URLSearchParams(\n        window.location.hash.replace(/^#/, \"\")\n    );\n\n    const isInvitation = fragment.get(\"type\") === \"invite\";\n    const accessToken = fragment.get(\"access_token\");\n    const refreshToken = fragment.get(\"refresh_token\");\n\n    // Remove invitation tokens from the address bar immediately.\n    window.history.replaceState(\n        null,\n        \"\",\n        window.location.pathname + window.location.search\n    );\n\n    if (!isInvitation || !accessToken || !refreshToken) {\n        message.textContent =\n            \"Open your valid student invitation email link.\";\n        return;\n    }\n\n    try {\n        const supabase = await createRecoveryClient();\n\n        const { data, error } = await supabase.auth.setSession({\n            access_token: accessToken,\n            refresh_token: refreshToken\n        });\n\n        if (error || !data?.session?.access_token) {\n            message.textContent =\n                \"Your invitation session could not be verified.\";\n            return;\n        }\n\n        const checkResponse = await fetch(\n            \"/api/student-activation/check\",\n            {\n                method: \"POST\",\n                headers: {\n                    \"Authorization\": `Bearer ${data.session.access_token}`\n                },\n                cache: \"no-store\"\n            }\n        );\n\n        if (!checkResponse.ok) {\n            message.textContent =\n                \"Student invitation verification failed.\";\n            return;\n        }\n\n        const checkResult = await checkResponse.json();\n\n        if (!checkResult.eligible || checkResult.status !== \"pending\") {\n            message.textContent =\n                \"This student account is not awaiting activation.\";\n            return;\n        }\n\n        if (!ACTIVATION_ENABLED) {\n            message.textContent =\n                \"Student identity verified. \" +\n                \"Password activation is awaiting final testing.\";\n            return;\n        }\n\n        form.hidden = false;\n        message.textContent =\n            \"Create a password to activate your student account.\";\n\n        let submitting = false;\n\n        form.addEventListener(\"submit\", async (event) => {\n            event.preventDefault();\n\n            if (submitting) return;\n\n            const password = passwordInput.value;\n            const confirmation = confirmationInput.value;\n\n            if (\n                password.length < 14 ||\n                password.length > 128 ||\n                password !== confirmation\n            ) {\n                message.textContent =\n                    \"Passwords must match and contain 14?128 characters.\";\n                return;\n            }\n\n            submitting = true;\n\n            const submitButton = form.querySelector(\n                'button[type=\"submit\"], input[type=\"submit\"]'\n            );\n\n            if (submitButton) submitButton.disabled = true;\n\n            try {\n                const { data: sessionData, error: sessionError } =\n                    await supabase.auth.getSession();\n\n                if (\n                    sessionError ||\n                    !sessionData?.session?.access_token\n                ) {\n                    throw new Error(\"Session unavailable\");\n                }\n\n                const response = await fetch(\n                    \"/api/student-activation/complete\",\n                    {\n                        method: \"POST\",\n                        headers: {\n                            \"Authorization\":\n                                `Bearer ${sessionData.session.access_token}`,\n                            \"Content-Type\": \"application/json\"\n                        },\n                        body: JSON.stringify({\n                            password,\n                            confirmation\n                        }),\n                        cache: \"no-store\"\n                    }\n                );\n\n                if (response.ok) {\n                    const result = await response.json();\n\n                    if (\n                        result.status === \"activated\" ||\n                        result.status === \"already_activated\"\n                    ) {\n                        form.hidden = true;\n                        message.textContent =\n                            \"Your student account is activated.\";\n                        return;\n                    }\n                }\n\n                if (response.status === 409) {\n                    form.hidden = true;\n                    message.textContent =\n                        \"Activation is being processed. \" +\n                        \"Please contact your teacher if this persists.\";\n                    return;\n                }\n\n                // A failed response can have an uncertain outcome.\n                // Never automatically retry a password update.\n                form.hidden = true;\n                message.textContent =\n                    \"Activation could not be confirmed. \" +\n                    \"Please contact your teacher.\";\n            } catch {\n                form.hidden = true;\n                message.textContent =\n                    \"Activation status is uncertain. \" +\n                    \"Please contact your teacher.\";\n            } finally {\n                passwordInput.value = \"\";\n                confirmationInput.value = \"\";\n                submitting = false;\n\n                if (submitButton) submitButton.disabled = false;\n            }\n        });\n    } catch {\n        message.textContent =\n            \"Unable to process your invitation securely.\";\n    }\n});\n";

async function scenario(status, password, confirmation) {
    let submitHandler;
    let ready;
    const calls = [];

    const readyPromise = new Promise(resolve => ready = resolve);

    const elements = {
        "activation-message": { textContent: "" },
        "activation-form": {
            hidden: true,
            addEventListener(event, handler) {
                if (event === "submit") submitHandler = handler;
            },
            querySelector() {
                return { disabled: false };
            }
        },
        "new-password": { value: password },
        "confirm-password": { value: confirmation }
    };

    const context = {
        URLSearchParams,
        Promise,
        document: {
            getElementById(id) {
                return elements[id] || null;
            },
            addEventListener(event, handler) {
                if (event === "DOMContentLoaded") {
                    Promise.resolve()
                        .then(handler)
                        .then(ready, ready);
                }
            }
        },
        window: {
            location: {
                hash: "#type=invite&access_token=mock&refresh_token=mock",
                pathname: "/accept-invite",
                search: ""
            },
            history: {
                replaceState() {}
            }
        },
        mockRecoveryClient: async () => ({
            auth: {
                setSession: async () => ({
                    data: { session: { access_token: "mock" } },
                    error: null
                }),
                getSession: async () => ({
                    data: { session: { access_token: "mock" } },
                    error: null
                })
            }
        }),
        fetch: async (url, options) => {
            calls.push({ url, options });

            if (url.endsWith("/check")) {
                return {
                    ok: true,
                    json: async () => ({
                        eligible: true,
                        status: "pending"
                    })
                };
            }

            return {
                ok: status === 200,
                status,
                json: async () => ({
                    status: "activated"
                })
            };
        }
    };

    vm.runInNewContext(source, context);
    await readyPromise;

    assert.equal(
        elements["activation-form"].hidden,
        false,
        "Form should be visible in test mode"
    );

    assert.equal(typeof submitHandler, "function");

    await submitHandler({ preventDefault() {} });

    return { elements, calls };
}

(async () => {
    const good = "ExamplePassword2026!";

    const success = await scenario(200, good, good);
    assert.match(
        success.elements["activation-message"].textContent,
        /account is activated/
    );
    assert.equal(
        success.calls.filter(c => c.url.endsWith("/complete")).length,
        1
    );
    assert.equal(success.elements["new-password"].value, "");
    assert.equal(success.elements["confirm-password"].value, "");
    console.log("Successful activation: PASS");

    const mismatch = await scenario(200, good, "DifferentPassword2026!");
    assert.equal(
        mismatch.calls.filter(c => c.url.endsWith("/complete")).length,
        0
    );
    console.log("Password mismatch blocked: PASS");

    const processing = await scenario(409, good, good);
    assert.match(
        processing.elements["activation-message"].textContent,
        /being processed/
    );
    assert.equal(
        processing.calls.filter(c => c.url.endsWith("/complete")).length,
        1
    );
    console.log("HTTP 409 handling: PASS");

    const uncertain = await scenario(503, good, good);
    assert.match(
        uncertain.elements["activation-message"].textContent,
        /could not be confirmed/
    );
    assert.equal(
        uncertain.calls.filter(c => c.url.endsWith("/complete")).length,
        1
    );
    console.log("HTTP 503 handling: PASS");

    console.log("TOTAL: 4/4 PASS");
})().catch(error => {
    console.error("TEST FAILED:", error.message);
    process.exitCode = 1;
});
