# Shared agent instructions

## Purpose

This repository is a reusable template for a four-person,
single-track hackathon team.

Current preparation work focuses on a small team-coordination
MCP server. The competition product has not been selected.

## Start here

Before claiming or changing work:

1. Read ORCHESTRATION.md.
2. Read REPO_STRUCTURE.md.
3. Read docs/HANDOFF.md.
4. Read your assigned task and your individual handoff, if present.
5. Confirm your human owner, agent ID, branch, and file scope.

Do not infer that planned files, tools, or commands already exist.

## Current scope

The first MCP milestone is a local, fixture-backed
get_team_state tool.

Keep MCP implementation under tools/team-mcp/.
Do not scaffold the competition application as part of this task.

## Collaboration

Use a separate checkout or worktree for each concurrent coding agent.
Modify only your assigned files.
Coordinate changes to shared contracts and dependencies.
Keep secrets and local session state out of Git.

Until board integration works, the human relays coordination messages.
Do not claim to have notified another agent without evidence.

## Human understanding

Before substantial implementation, explain the proposed approach
and one simpler alternative.

Work in small increments. Explain the actual execution path,
important choices, verification, and limitations.

Ask the human to predict behavior before revealing the answer
during teaching walkthroughs.

## Verification

Use commands documented as implemented in the relevant README.
Record which checks actually ran and their results.
Do not report planned checks as passing checks.