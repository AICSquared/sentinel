import "server-only";

import { demoMode } from "@/lib/demo";
import { createClient } from "@/lib/supabase/server";
import type { AttackType } from "./contract";

/** One row of the INSERT-ONLY audit_log (supabase/migrations/20261114000000_audit_log.sql). */
export type AuditEntry = {
  agent_id: string;
  risk: number;
  attack_type: AttackType | null;
  /** What was recommended (by Sentinel) or decided (by a human): e.g. "recommend_quarantine", "approved". */
  action: string;
  /** "sentinel" or a human id. */
  decided_by: string;
  detail?: Record<string, unknown>;
};

export type AuditResult = { written: number; skipped: boolean; error?: string };

/**
 * Appends rows to audit_log. The table has no UPDATE or DELETE policy, so rows can never be
 * changed or removed from the app. In demo mode (or without Supabase keys) it writes nothing
 * and says so, so the stage demo never depends on the network.
 */
export async function writeAudit(entries: AuditEntry[]): Promise<AuditResult> {
  if (entries.length === 0) return { written: 0, skipped: false };
  if (demoMode) return { written: 0, skipped: true };
  try {
    const supabase = await createClient();
    const { error } = await supabase.from("audit_log").insert(entries);
    if (error) return { written: 0, skipped: false, error: error.message };
    return { written: entries.length, skipped: false };
  } catch (e) {
    return { written: 0, skipped: false, error: e instanceof Error ? e.message : "audit write failed" };
  }
}
