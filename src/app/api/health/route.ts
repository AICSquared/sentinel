import { demoMode } from "@/lib/demo";
import { hasSupabase } from "@/lib/supabase/env";

/** Quick check before a demo: is Supabase connected, and is demo mode on? */
export function GET() {
  return Response.json({ ok: true, supabase: hasSupabase, demo: demoMode });
}
