# Connecteam

Connecteam is a workforce app for deskless teams. This connector reads schedules, users, jobs, and availability through the Connecteam REST API. It replaces browser reads for those items. The browser stays the fallback for anything that only exists in the Connecteam web UI.

## Connection status

- Not live yet. No real API call has been made with this connector.
- The connection is registered through the Muse Secure Vault flow for provider connecteam. The key goes in on the secure page, never in chat, files, or code.
- The key must come from a Rhino Connecteam account owner or admin. Employee accounts do not mint API keys. Ask Cory or another account owner for the key.
- API access needs the Expert plan or higher on at least one hub. If the account is below Expert, the API keys tab does not appear in Connecteam settings.
- Use the default host for Rhino Squad. Australian hosted accounts use the AU host instead.

## How to run the server

- The server is Python standard library only. It needs no installs.
- Run it with this command from the connector folder.
- `CONNECTEAM_API_KEY=<key> python3 bin/connecteam-mcp.py`
- The server speaks MCP over stdio with newline delimited JSON-RPC.
- Set `CONNECTEAM_BASE_URL` to `https://api-au.connecteam.com` only for Australian hosted accounts. The default is `https://api.connecteam.com`.
- The server never prints or logs the key. Error messages never include it.

## Tools

- `get_account` reads account details, company name and company id. Path verified in official docs.
- `list_users` lists users with filters for ids, status, full names, and phone numbers. Pagination uses limit and offset. Path verified in official docs.
- `list_jobs` lists jobs for instance ids, where an instance id is a scheduler id or a time clock id. Deleted jobs are included by default. Path verified in official docs.
- `list_shifts` lists shifts in one scheduler. The collection path is verified through the create shift endpoint. The GET method on that collection still needs one live confirmation.
- `get_user_unavailability` reads user unavailability records. Path verified in official docs.
- `get_shift_auto_assign` reads the status of a shift auto-assign request. Path verified in official docs.
- `create_shift` creates a shift in a scheduler. This is a write and it is gated.
- `delete_shift` deletes one shift. This is a write and it is gated.
- `generate_upload_url` returns a pre-signed upload URL for a file. The feature type must be one of chat, shiftscheduler, users, quicktasks, documents. Path verified in official docs.

## Write gate

- A write tool refuses to run unless the call passes `confirm=true`.
- A refused write sends no HTTP request at all. The mock tests prove this.
- Clock in, clock out, sending chat messages, submitting forms, and changing settings have no tools in this version. They need an explicit decision before any of them is added.

## Rate limits and errors

- Connecteam rate limits per plan and returns HTTP 429 with rate limit headers. The exact official numbers were not confirmed from the rate limiting doc page, so no numbers are claimed here.
- The server passes a 429 through with the Retry-After value when the API sends one.
- A 401 means the key is wrong, expired, or lacks access to that hub.
- A 403 means the key lacks access to that hub or the account plan does not include API access.
- A 404 on a pending path means the path guess was wrong or the record does not exist. Report it and do not retry blindly.

## What was verified

- The server compiles clean with py_compile.
- The mock test suite passes 20 of 20 checks against a local mock HTTP server. No real Connecteam call was made.
- The suite covers initialize, tools/list with all 9 tools, every read tool, the write gate refusing unconfirmed writes with zero requests sent, confirmed writes posting the right body, unknown tool errors, missing argument errors, 401 mapping, 429 mapping with Retry-After, and tools/list working without a key while tools/call fails cleanly.
- Run the suite with this command from the connector folder.
- `python3 tests/test_connecteam_mcp.py`

## What was not verified

- No live call has been made. The first live call is the proof step below.
- The GET method on the shifts collection path is not confirmed live.
- These families exist in the official API access table but their exact paths were not confirmed from the official reference pages, so they have no tools yet. Schedulers list, time clock, chat, forms, tasks, time off reads, publishers, daily info, smart groups, and custom fields.
- Adding one of those families means confirming its exact path from the official API reference first, then adding the tool, then extending the mock tests.

## First live proof

- Run this call first once the key exists. It is harmless and read only.
- `get_account` with no arguments. It should return the Rhino Squad company name and id.
- Then call `list_shifts` with a real scheduler id. If it returns shifts, the GET method is confirmed. If it returns 404, the shifts list path needs a correction from the official reference.
- Then confirm one path per missing family from the official API reference before adding its tool.
- Keep the browser fallback until the live proof passes. Do not present the connector as working before that call succeeds.
