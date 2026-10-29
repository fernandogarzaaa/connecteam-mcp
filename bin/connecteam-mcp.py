#!/usr/bin/env python3
"""Connecteam MCP server (stdio, JSON-RPC 2.0, standard library only).

Reads the API key from CONNECTEAM_API_KEY and the base URL from
CONNECTEAM_BASE_URL (default https://api.connecteam.com, use
https://api-au.connecteam.com for Australian hosted accounts).
The key is never printed, logged, or included in any output.

Tool paths marked VERIFIED were seen in Connecteam official docs.
One tool, list_shifts, uses a collection path verified through the
create shift endpoint, while the GET method on that collection still
needs one live confirmation. That flag is in the tool description and
in CONNECTOR.md.

Write tools (create_shift, delete_shift) refuse to run unless the
caller passes confirm=true. A refused write sends no HTTP request.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_NAME = "connecteam-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_BASE_URL = "https://api.connecteam.com"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_CHARS = 200000


def tool(name, description, properties, required, method, path, gated=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
        "method": method,
        "path": path,
        "gated": gated,
    }


STR = {"type": "string"}
STR_ARR = {"type": "array", "items": {"type": "string"}}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
OBJ = {"type": "object"}

TOOLS = [
    tool(
        "get_account",
        "Get Connecteam account details: company name and company id. "
        "VERIFIED path.",
        {},
        [],
        "GET",
        "/me",
    ),
    tool(
        "list_users",
        "List users with optional filters. Pagination uses limit and offset. "
        "VERIFIED path.",
        {
            "userIds": STR_ARR,
            "userStatus": STR,
            "fullNames": STR_ARR,
            "phoneNumbers": STR_ARR,
            "limit": INT,
            "offset": INT,
        },
        [],
        "GET",
        "/users/v1/users",
    ),
    tool(
        "list_jobs",
        "List job objects for one or more instance ids (a scheduler id or a "
        "time clock id). Deleted jobs are included by default. "
        "VERIFIED path.",
        {
            "instanceIds": STR_ARR,
            "jobIds": STR_ARR,
            "jobNames": STR_ARR,
            "jobCodes": STR_ARR,
            "includeDeleted": BOOL,
            "limit": INT,
            "offset": INT,
        },
        [],
        "GET",
        "/jobs/v1/jobs",
    ),
    tool(
        "list_shifts",
        "List shifts in one scheduler. The collection path is VERIFIED "
        "through the create shift endpoint. The GET method on this "
        "collection still needs one live confirmation.",
        {"schedulerId": STR},
        ["schedulerId"],
        "GET",
        "/scheduler/v1/schedulers/{schedulerId}/shifts",
    ),
    tool(
        "get_user_unavailability",
        "Get user unavailability records for schedulers. VERIFIED path.",
        {"userIds": STR_ARR, "limit": INT, "offset": INT},
        [],
        "GET",
        "/scheduler/v1/schedulers/user-unavailability",
    ),
    tool(
        "get_shift_auto_assign",
        "Get the status of a shift auto-assign request. VERIFIED path.",
        {"schedulerId": STR, "requestId": STR},
        ["schedulerId", "requestId"],
        "GET",
        "/scheduler/v1/schedulers/{schedulerId}/shifts/auto-assign/{requestId}",
    ),
    tool(
        "create_shift",
        "Create a shift in a scheduler. WRITE: refused unless confirm=true "
        "is passed. VERIFIED path.",
        {
            "schedulerId": STR,
            "startTime": STR,
            "endTime": STR,
            "title": STR,
            "timezone": STR,
            "isPublished": BOOL,
            "jobId": STR,
            "assignedUserId": STR,
            "notes": STR_ARR,
            "locationData": OBJ,
            "confirm": BOOL,
        },
        ["schedulerId", "startTime", "endTime", "title"],
        "POST",
        "/scheduler/v1/schedulers/{schedulerId}/shifts",
        gated=True,
    ),
    tool(
        "delete_shift",
        "Delete one shift. WRITE: refused unless confirm=true is passed. "
        "VERIFIED path.",
        {"schedulerId": STR, "shiftId": STR, "confirm": BOOL},
        ["schedulerId", "shiftId"],
        "DELETE",
        "/scheduler/v1/schedulers/{schedulerId}/shifts/{shiftId}",
        gated=True,
    ),
    tool(
        "generate_upload_url",
        "Generate a pre-signed upload URL for a file. featureType must be "
        "one of chat, shiftscheduler, users, quicktasks, documents. "
        "VERIFIED path.",
        {
            "featureType": {
                "type": "string",
                "enum": ["chat", "shiftscheduler", "users", "quicktasks", "documents"],
            },
            "fileName": STR,
            "fileSize": INT,
        },
        ["featureType"],
        "POST",
        "/attachments/v1/files/generate-upload-url",
    ),
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def public_tool(t):
    return {
        "name": t["name"],
        "description": t["description"],
        "inputSchema": t["inputSchema"],
    }


def api_call(spec, args):
    api_key = os.environ.get("CONNECTEAM_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "CONNECTEAM_API_KEY is not set. Set it in the environment before "
            "calling Connecteam tools."
        )
    base = os.environ.get("CONNECTEAM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    path = spec["path"]
    remaining = dict(args)
    for key in list(remaining):
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, urllib.parse.quote(str(remaining.pop(key)), safe=""))
    method = spec["method"]
    url = base + path
    body = None
    headers = {"Accept": "application/json", "X-API-KEY": api_key}
    if method == "GET":
        query = {k: v for k, v in remaining.items() if v is not None}
        if query:
            url = url + "?" + urllib.parse.urlencode(query, doseq=True)
    else:
        body = json.dumps(remaining).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        if err.code == 401:
            raise RuntimeError(
                "Authentication failed (401). The API key may be wrong, "
                "expired, or lack access to this hub."
            )
        if err.code == 403:
            raise RuntimeError(
                "Forbidden (403). The key may lack access to this hub, or "
                "the account plan may not include API access."
            )
        if err.code == 429:
            retry = err.headers.get("Retry-After", "")
            hint = " Retry-After: " + retry + "." if retry else ""
            raise RuntimeError("Rate limited (429)." + hint)
        if err.code == 404:
            raise RuntimeError(
                "Not found (404). The path may be wrong or the record may "
                "not exist. Response: " + raw[:500]
            )
        raise RuntimeError("Connecteam API error %d. Response: %s" % (err.code, raw[:500]))
    except urllib.error.URLError as err:
        raise RuntimeError("Network error reaching Connecteam: %s" % err.reason)
    if len(raw) > MAX_RESPONSE_CHARS:
        raw = raw[:MAX_RESPONSE_CHARS] + "\n[truncated at %d chars]" % MAX_RESPONSE_CHARS
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def handle_tools_call(params):
    name = params.get("name", "")
    args = params.get("arguments", {}) or {}
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return {"content": [{"type": "text", "text": "Unknown tool: " + name}], "isError": True}
    missing = [r for r in spec["inputSchema"]["required"] if r not in args]
    if missing:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Missing required argument: " + ", ".join(missing),
                }
            ],
            "isError": True,
        }
    if spec["gated"] and args.get("confirm") is not True:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Write gate: pass confirm=true to run this write. "
                    "Nothing was sent to Connecteam.",
                }
            ],
            "isError": True,
        }
    call_args = {k: v for k, v in args.items() if k != "confirm"}
    try:
        result = api_call(spec, call_args)
    except RuntimeError as err:
        return {"content": [{"type": "text", "text": str(err)}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


def handle(request):
    method = request.get("method", "")
    req_id = request.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [public_tool(t) for t in TOOLS]},
        }
    if method == "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": handle_tools_call(request.get("params", {}) or {}),
        }
    if method.startswith("notifications/"):
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not found: " + method},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
