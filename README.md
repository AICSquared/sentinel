# Hackathon Agent Template

A reusable starting point for a four-person hackathon team
using multiple coding agents on one project.

## Current status

Template preparation. The competition application is not built.

The first development milestone is a local MCP server exposing
a fixture-backed get_team_state tool.

## Documentation

- [Shared agent instructions](AGENTS.md)
- [Team workflow](ORCHESTRATION.md)
- [Repository structure](REPO_STRUCTURE.md)
- [Current team state](docs/HANDOFF.md)

## Coordination MCP server

Planned location: tools/team-mcp/

Setup and verified commands will be documented in that
directory's README once implemented.

## Principles

- One human owns every task.
- Agents work within explicit file boundaries.
- Completion requires evidence and human understanding.
- Simulated, replayed, and live behavior are labeled honestly.