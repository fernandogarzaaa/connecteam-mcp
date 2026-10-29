# Connecteam MCP

This is an MCP server for the Connecteam REST API. It lets an AI assistant read Connecteam data directly instead of reading it through a browser. It is written in Python standard library only. It needs no installs. It speaks MCP over stdio.

## What it can do

- Read account details, users, jobs, shifts, user unavailability, and shift auto-assign status.
- Create and delete shifts. Both writes are gated. They refuse to run unless the call passes confirm=true.
- Generate a pre-signed upload URL for a file.

## What it needs

- Python 3.
- A Connecteam API key. Only a Connecteam account owner or admin can generate one. API access needs the Expert plan or higher on at least one hub.
- The key goes in the CONNECTEAM_API_KEY environment variable. It never goes in this repo, in chat, or in logs.
- The default API host is api.connecteam.com. Australian hosted accounts use api-au.connecteam.com instead.

## Run it

Run this command from the repo root. Replace the key value with a real key.

- `CONNECTEAM_API_KEY=<key> python3 bin/connecteam-mcp.py`

Point an MCP client at that command as a stdio server. Set CONNECTEAM_API_KEY and optionally CONNECTEAM_BASE_URL in the server environment.

## Verify it

Run the mock tests first. They use a local mock server. They make no real Connecteam call.

- `python3 tests/test_connecteam_mcp.py`

Then prove the live connection with a harmless read-only call.

- Call get_account with no arguments. It should return the company name and company id.
- Then call list_shifts with a real scheduler id. If it returns shifts, the shifts list path is confirmed live.

## Limits, stated plainly

- The shifts list path is verified through the create shift endpoint. The GET method on that collection still needs one live confirmation.
- These families have no tools yet. Their exact API paths were not confirmed from the official reference. Schedulers list, time clock, chat, forms, tasks, time off reads, publishers, daily info, smart groups, and custom fields.
- There are no tools for clock in, clock out, sending chat messages, or submitting forms. Do not invent them.
- Connecteam rate limits per plan and returns HTTP 429. Respect the Retry-After value when one is sent.

## Files

- CONNECTOR.md is the full connector doc. It lists every tool, the write gate, error meanings, and the live proof steps.
- connector.yaml is the connector manifest.
- bin/connecteam-mcp.py is the server.
- tests/test_connecteam_mcp.py is the mock test suite.
