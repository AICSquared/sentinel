"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { after } from "next/server";
import { runJob } from "@/lib/jobs";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient, getUser } from "@/lib/supabase/server";
import { tracks } from "@/lib/tracks";

const validTracks = new Set<string>([...tracks.map((t) => t.slug), "shared"]);

/** Creates a job, runs it after the response is sent, and refreshes the page. */
export async function createJob(form: FormData) {
  const user = await getUser();
  if (!user) redirect("/login");

  const track = String(form.get("track") ?? "shared");
  const note = String(form.get("note") ?? "").slice(0, 500);
  if (!validTracks.has(track)) redirect("/example?error=Unknown%20track");

  const supabase = await createClient();
  const { data: job, error } = await supabase
    .from("jobs")
    .insert({ user_id: user.id, track, kind: "demo", input: { note } })
    .select("id")
    .single();
  if (error || !job) redirect(`/example?error=${encodeURIComponent(error?.message ?? "Could not create the job")}`);

  // Run the work after the response is sent. after() runs outside the request, so it
  // uses the secret-key client when available; otherwise run it before responding.
  const hasSecret = Boolean(process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY);
  if (hasSecret) after(() => runJob(createAdminClient(), job.id));
  else await runJob(supabase, job.id);

  revalidatePath("/example");
}

export async function deleteJob(form: FormData) {
  const supabase = await createClient();
  await supabase.from("jobs").delete().eq("id", String(form.get("id")));
  revalidatePath("/example");
}
