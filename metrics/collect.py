#!/usr/bin/env python3
"""Collect AI-usage metrics for the hackathon report. Standard library only; needs `git` and `gh`.

Usage (from the repo root):  python3 metrics/collect.py --who alex     (teammates: --who brandon | noah | stephen)
If your Claude Code session was started outside this repo, point at that session's log file(s) only:
    python3 metrics/collect.py --who brandon --session ~/.claude/projects/-Users-you/<session-id>.jsonl

Writes metrics/data/<who>.json with COUNTS AND TIMESTAMPS ONLY (no message text), from:
  1. this machine's Claude Code session logs for this repo (prompts, replies, tool calls, tokens, active time)
  2. git history (commits, lines added/removed per author and folder)
  3. the board issue (posts per agent, by label: ACK / DONE / BLOCKED / STATUS / OFFLINE)
  4. GitHub issues and PRs (time from issue opened to PR merged, i.e. time per task)
Run it again at any time; it overwrites its own file with fresh numbers.
"""
import argparse, collections, json, os, re, subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAP_MIN = 10            # a pause longer than this does not count as active time


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def active_minutes(times):
    times = sorted(times)
    return round(sum(min((b - a).total_seconds(), GAP_MIN * 60) for a, b in zip(times, times[1:])) / 60, 1)


def chat_metrics(session_files=None):
    proj = Path.home() / ".claude" / "projects" / str(ROOT).replace("/", "-")
    if session_files:   # explicit sessions only (plus their subagents); nothing else from that folder is read
        files = []
        for f in map(Path, session_files):
            files += [f] + sorted((f.parent / f.stem / "subagents").glob("*.jsonl"))
    else:
        files = []
        # this repo's folder plus its worktree sessions (Claude Code names them <repo>--claude-worktrees-<name>)
        for d in [proj] + sorted(proj.parent.glob(proj.name + "--claude-worktrees-*")):
            files += sorted(d.glob("*.jsonl")) + sorted(d.glob("*/subagents/*.jsonl"))
    out = {"session_dir_found": proj.exists(), "sessions": []}
    # a resumed or forked session copies the earlier conversation into a new log: count each reply and prompt once
    seen_req, seen_prompt = set(), set()
    for f in files:
        prompts = replies = 0
        tools = collections.Counter()
        tok = collections.Counter()
        times, models = [], collections.Counter()
        for line in open(f, errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("timestamp"):
                times.append(ts(d["timestamp"]))
            m = d.get("message") or {}
            if d.get("type") == "user" and not d.get("isMeta"):
                c = m.get("content")
                if isinstance(c, str) and not c.lstrip().startswith(("<", "[Request interrupted", "Caveat")):
                    key = d.get("uuid") or (d.get("timestamp"), c[:40])
                    if key not in seen_prompt:
                        seen_prompt.add(key)
                        prompts += 1
            if d.get("type") == "assistant":
                for block in m.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools[block.get("name", "?")] += 1
                rid = d.get("requestId") or m.get("id")
                if rid and rid not in seen_req:
                    seen_req.add(rid)
                    replies += 1
                    models[m.get("model", "?")] += 1
                    u = m.get("usage") or {}
                    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                        tok[k] += int(u.get(k) or 0)
                    tok["thinking_tokens"] += int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
        if not times:
            continue
        out["sessions"].append({
            "file": f.name, "kind": "subagent" if "subagents" in str(f) else "main",
            "start": min(times).isoformat(), "end": max(times).isoformat(),
            "active_minutes": active_minutes(times),
            "human_prompts": prompts, "model_responses": replies,
            "tool_calls_total": sum(tools.values()), "tool_calls_by_name": dict(tools.most_common()),
            "tokens": dict(tok), "models": dict(models),
        })
    tot = collections.Counter()
    for s in out["sessions"]:
        tot.update({k: v for k, v in s["tokens"].items()})
        tot["human_prompts"] += s["human_prompts"]; tot["model_responses"] += s["model_responses"]
        tot["tool_calls"] += s["tool_calls_total"]
    out["totals"] = dict(tot)
    return out


def git_metrics():
    log = sh("git", "log", "--all", "--no-merges", "--numstat", "--format=@%H|%an|%aI|%s")
    commits, per_author, per_folder, cur = [], collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), None
    for line in log.splitlines():
        if line.startswith("@"):
            h, an, at, subj = line[1:].split("|", 3)
            cur = {"sha": h[:7], "author": an, "time": at, "subject_len": len(subj), "files": 0}
            commits.append(cur); per_author[an]["commits"] += 1
        elif line.strip() and cur:
            a, r, path = line.split("\t", 2)
            if a == "-":
                continue
            kind = "notebook_json" if path.endswith(".ipynb") else "log_data" if path.endswith((".csv", ".jsonl")) else "code_docs"
            cur["files"] += 1
            per_author[cur["author"]][f"{kind}_added"] += int(a); per_author[cur["author"]][f"{kind}_removed"] += int(r)
            per_folder[path.split("/")[0] if "/" in path else "(root)"][f"{kind}_added"] += int(a)
    return {"commits": len(commits), "per_author": {k: dict(v) for k, v in per_author.items()},
            "per_folder": {k: dict(v) for k, v in per_folder.items()},
            "first_commit": min((c["time"] for c in commits), default=None),
            "last_commit": max((c["time"] for c in commits), default=None),
            "note": "notebook_json lines are generated notebook files; code_docs is hand/agent-written source and docs"}


def board_metrics():
    repo = sh("gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").strip()
    env = {}
    if (ROOT / ".board.env").exists():
        env = dict(l.split("=", 1) for l in (ROOT / ".board.env").read_text().split() if "=" in l)
    issues = (os.environ.get("BOARD_WATCH") or env.get("BOARD_WATCH") or "1").split(",")
    comments = []
    for issue in issues:   # every channel this team watches (Sentinel: #1 lead, #2 cisco)
        raw = sh("gh", "api", "--paginate", f"repos/{repo}/issues/{issue.strip()}/comments?per_page=100")
        try:
            comments += [dict(c, channel=int(issue)) for c in json.loads(raw.replace("][", ","))]
        except ValueError:
            return {"error": f"could not read board issue {issue}"}
    by_agent, labels, times = collections.Counter(), collections.Counter(), []
    for c in comments:
        body = c.get("body", "")
        m = re.match(r"\[([^\]]+)\]", body)
        by_agent[m.group(1) if m else c["user"]["login"]] += 1
        for lab in ("ACK", "DONE", "BLOCKED", "STATUS", "OFFLINE"):
            if re.search(rf"\b{lab}\b", body[:200]):
                labels[lab] += 1
        labels["mentions"] += len(re.findall(r"@\w", body))
        times.append(c["created_at"])
    return {"posts": len(comments), "by_agent": dict(by_agent), "labels": dict(labels), "by_channel": dict(collections.Counter(c["channel"] for c in comments)),
            "first_post": min(times, default=None), "last_post": max(times, default=None)}


def task_metrics():
    raw = sh("gh", "pr", "list", "--state", "all", "--limit", "100", "--json",
             "number,title,author,createdAt,mergedAt,additions,deletions,headRefName")
    prs = json.loads(raw or "[]")
    issues = {i["number"]: i for i in json.loads(sh("gh", "issue", "list", "--state", "all", "--limit", "100",
                                                    "--json", "number,title,createdAt,closedAt") or "[]")}
    tasks = []
    for p in prs:
        n = re.match(r"(\d+)-", p["headRefName"])
        iss = issues.get(int(n.group(1))) if n else None
        start = iss["createdAt"] if iss else p["createdAt"]
        tasks.append({"pr": p["number"], "title": p["title"], "author": p["author"]["login"],
                      "merged": bool(p["mergedAt"]), "additions": p["additions"], "deletions": p["deletions"],
                      "minutes_issue_to_merge": round((ts(p["mergedAt"]) - ts(start)).total_seconds() / 60, 1) if p["mergedAt"] else None})
    return {"prs": len(prs), "issues": len(issues), "tasks": tasks}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True, help="alex, brandon, noah or stephen")
    ap.add_argument("--session", nargs="*", help="specific Claude Code session .jsonl file(s) to read instead of this repo's folder")
    args = ap.parse_args(); who = args.who
    data = {"who": who, "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "chat": chat_metrics(args.session), "git": git_metrics(), "board": board_metrics(), "tasks": task_metrics()}
    out = ROOT / "metrics" / "data" / f"{who}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    t = data["chat"]["totals"]
    print(f"wrote {out.relative_to(ROOT)}: {t.get('human_prompts', 0)} prompts, {t.get('model_responses', 0)} model responses, "
          f"{t.get('tool_calls', 0)} tool calls, {t.get('output_tokens', 0):,} output tokens, "
          f"{data['git']['commits']} commits, {data['board'].get('posts')} board posts")
