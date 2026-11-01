"use strict";

// KRISI Biology Studio
// Supabase browser authentication client.

import { createClient } from "@supabase/supabase-js";

export async function createRecoveryClient() {
    const response = await fetch("/auth/public-config", {
        method: "GET",
        cache: "no-store"
    });

    if (!response.ok) {
        throw new Error("Authentication configuration unavailable.");
    }

    const config = await response.json();

    if (
        !config.supabase_url ||
        !config.supabase_publishable_key
    ) {
        throw new Error("Incomplete authentication configuration.");
    }

    return createClient(
        config.supabase_url,
        config.supabase_publishable_key,
        {
            auth: {
                persistSession: false,
                autoRefreshToken: false,
                detectSessionInUrl: true,
                skipAutoInitialize: true
            }
        }
    );
}
