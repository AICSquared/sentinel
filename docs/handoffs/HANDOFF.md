# Current team state

## Phase

Template preparation and MCP learning.

## Current milestone

Connect a local MCP server to Claude Code and successfully
call a fixture-backed get_team_state tool.

## Current assignment

- Human owner: Alex Williams
- Agent ID: alex-claude
- File scope: tools/team-mcp/
- Branch: Record the actual branch before implementation

## Accepted direction

- One competition track and one product.
- Four human component owners during the hackathon.
- Shared instructions live in AGENTS.md and the linked guides.
- First MCP transport: local stdio.
- First MCP tool: get_team_state.
- First data source: a small JSON fixture.

## Not implemented yet

- MCP server
- GitHub-backed tool operations
- Message routing and independent cursors
- Pi hosting
- Cluster inference
- Competition application

## Next action

Follow the meeting's SDK setup and create the smallest
fixture-backed server under tools/team-mcp/.

## Verification

No implementation checks have run yet.

## Open decisions

- Selected competition track and problem
- Remaining team ownership assignments
- SDK version used by the meeting
- Event rules governing advance preparation