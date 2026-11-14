import { hasSupabase } from "@/lib/supabase/env";

/**
 * Demo mode: track pages read the bundled sample data in src/app/<track>/_data/ instead of
 * live services, so a demo never depends on venue Wi-Fi or an outside service.
 * On when NEXT_PUBLIC_DEMO_MODE=1, and automatically when Supabase isn't set up.
 */
export const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1" || !hasSupabase;
