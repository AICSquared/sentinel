-- Append-only audit log for Sentinel. Insert allowed; UPDATE and DELETE are not,
-- so the log is tamper-evident at the database level (the control we recommend in the pitch).

create table if not exists audit_log (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  agent_id    text not null,
  risk        int  not null,
  attack_type text,
  action      text not null,          -- recommended / human decision
  decided_by  text,                   -- 'sentinel' or a human id
  detail      jsonb
);

alter table audit_log enable row level security;

-- INSERT only. No update or delete policy exists, so rows can never be changed or removed from the client.
create policy audit_insert on audit_log
  for insert to anon, authenticated
  with check (true);

create policy audit_read on audit_log
  for select to anon, authenticated
  using (true);
