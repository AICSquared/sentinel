import "server-only";

import { demoMode } from "@/lib/demo";

export type AlertResult = { sent: boolean; skipped: boolean; error?: string };

// Only real Discord webhook URLs, so a bad env value can't make the server call anything else.
const DISCORD_WEBHOOK = /^https:\/\/(?:discord\.com|discordapp\.com|ptb\.discord\.com|canary\.discord\.com)\/api\/webhooks\/\d+\/[\w-]+$/;

/**
 * Posts one plain-text alert to the team's Discord channel (DISCORD_WEBHOOK_URL, server-only).
 * Skipped in demo mode or when the URL is unset. Never throws; times out after 3 s.
 */
export async function sendAlert(text: string): Promise<AlertResult> {
  const url = process.env.DISCORD_WEBHOOK_URL ?? "";
  if (demoMode || !url) return { sent: false, skipped: true };
  if (!DISCORD_WEBHOOK.test(url)) return { sent: false, skipped: true, error: "DISCORD_WEBHOOK_URL is not a Discord webhook" };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      // No @everyone / role pings, whatever the text says.
      body: JSON.stringify({ content: text.slice(0, 1900), allowed_mentions: { parse: [] } }),
      signal: AbortSignal.timeout(3000),
    });
    return res.ok ? { sent: true, skipped: false } : { sent: false, skipped: false, error: `Discord replied ${res.status}` };
  } catch (e) {
    return { sent: false, skipped: false, error: e instanceof Error ? e.message : "alert failed" };
  }
}
