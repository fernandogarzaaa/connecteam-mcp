#!/usr/bin/env python3
"""Mock backend tests for the Connecteam MCP server.

Spawns bin/connecteam-mcp.py against a local mock HTTP server, speaks
JSON-RPC over stdio, and checks initialize, tools/list, tools/call,
the write gate, and error mapping. No real Connecteam call is made.
The test key is a fake value and is never printed.
"""

import json
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "..", "bin", "connecteam-mcp.py")
TEST_KEY = "test-key-xyz"

EXPECTED_TOOLS = {
    "get_account",
    "list_users",
    "list_jobs",
    "list_shifts",
    "get_user_unavailability",
    "get_shift_auto_assign",
    "create_shift",
    "delete_shift",
    "generate_upload_url",
}


class MockHandler(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *args):
        pass

    def _record(self, body):
        entry = {
            "method": self.command,
            "path": self.path,
            "has_key": "X-Api-Key" in self.headers or "X-API-KEY" in self.headers,
            "body": body,
        }
        self.server.requests.append(entry)

    def _send(self, code, payload, extra=None):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _route(self, body):
        if self.mode == "401":
            self._send(401, {"error": "unauthorized"})
            return
        if self.mode == "429":
            self._send(429, {"error": "slow down"}, {"Retry-After": "5"})
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        if self.command == "GET" and path == "/me":
            self._send(200, {"data": {"companyName": "Rhino Squad Test", "companyId": "123"}})
        elif self.command == "GET" and path == "/users/v1/users":
            self._send(200, {"data": {"users": [], "echo_query": query}})
        elif self.command == "GET" and path == "/jobs/v1/jobs":
            self._send(200, {"data": {"jobs": []}})
        elif self.command == "GET" and path == "/scheduler/v1/schedulers/user-unavailability":
            self._send(200, {"data": []})
        elif self.command == "GET" and path.endswith("/shifts") and "/schedulers/" in path:
            self._send(200, {"data": {"shifts": []}})
        elif self.command == "GET" and "/auto-assign/" in path:
            self._send(200, {"data": {"status": "completed"}})
        elif self.command == "POST" and path.endswith("/shifts"):
            self._send(200, {"data": {"shiftId": "SH1", "echo_body": body}})
        elif self.command == "DELETE" and "/shifts/" in path:
            self._send(200, {"data": {}})
        elif self.command == "POST" and path == "/attachments/v1/files/generate-upload-url":
            self._send(200, {"data": {"uploadUrl": "https://example.invalid/upload"}})
        else:
            self._send(404, {"error": "no mock route"})

    def _handle(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        body = None
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                body = {"raw": raw.decode("utf-8", "replace")}
        self._record(body)
        self._route(body)

    do_GET = _handle
    do_POST = _handle
    do_DELETE = _handle


def start_mock(mode):
    MockHandler.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class McpClient:
    def __init__(self, base_url, api_key=None):
        env = dict(os.environ)
        env["CONNECTEAM_BASE_URL"] = base_url
        if api_key is None:
            env.pop("CONNECTEAM_API_KEY", None)
        else:
            env["CONNECTEAM_API_KEY"] = api_key
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.next_id = 1

    def call(self, method, params=None):
        req = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        self.next_id += 1
        if params is not None:
            req["params"] = params
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def tool(self, name, args):
        resp = self.call("tools/call", {"name": name, "arguments": args})
        result = resp["result"]
        text = result["content"][0]["text"]
        return result.get("isError", False), text

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        self.proc.wait(timeout=10)


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print("%s %s %s" % (status, name, detail))
    return cond


def run_ok_suite():
    server = start_mock("ok")
    base = "http://127.0.0.1:%d" % server.server_address[1]
    client = McpClient(base, TEST_KEY)
    ok = True
    try:
        resp = client.call("initialize", {"protocolVersion": "2024-11-05"})
        result = resp["result"]
        ok &= check(
            "initialize",
            result["serverInfo"]["name"] == "connecteam-mcp"
            and result["protocolVersion"] == "2024-11-05",
            result["serverInfo"],
        )
        resp = client.call("tools/list")
        names = {t["name"] for t in resp["result"]["tools"]}
        ok &= check("tools/list", names == EXPECTED_TOOLS, sorted(names))
        err, text = client.tool("get_account", {})
        data = json.loads(text) if not err else {}
        ok &= check(
            "get_account",
            not err and data["data"]["companyName"] == "Rhino Squad Test",
            text[:120],
        )
        err, text = client.tool("list_users", {"fullNames": ["Rhino Test"], "limit": 5})
        data = json.loads(text) if not err else {}
        echo = data.get("data", {}).get("echo_query", {})
        ok &= check(
            "list_users query passthrough",
            not err and echo.get("fullNames") == ["Rhino Test"] and echo.get("limit") == ["5"],
            str(echo),
        )
        err, text = client.tool("list_shifts", {"schedulerId": "S1"})
        ok &= check("list_shifts", not err and "shifts" in text, text[:120])
        err, text = client.tool("get_user_unavailability", {"userIds": ["U1"]})
        ok &= check("get_user_unavailability", not err, text[:120])
        err, text = client.tool(
            "get_shift_auto_assign", {"schedulerId": "S1", "requestId": "REQ1"}
        )
        ok &= check("get_shift_auto_assign", not err and "completed" in text, text[:120])
        err, text = client.tool("list_jobs", {"instanceIds": ["S1"]})
        ok &= check("list_jobs", not err and "jobs" in text, text[:120])
        before = len(server.requests)
        err, text = client.tool(
            "create_shift",
            {"schedulerId": "S1", "startTime": "2026-10-30T00:00:00Z",
             "endTime": "2026-10-30T08:00:00Z", "title": "Test shift"},
        )
        sent = len(server.requests) - before
        ok &= check(
            "create_shift refused without confirm",
            err and "confirm=true" in text and sent == 0,
            "sent=%d" % sent,
        )
        err, text = client.tool(
            "create_shift",
            {"schedulerId": "S1", "startTime": "2026-10-30T00:00:00Z",
             "endTime": "2026-10-30T08:00:00Z", "title": "Test shift", "confirm": True},
        )
        posted = [r for r in server.requests if r["method"] == "POST"]
        body = posted[-1]["body"] if posted else {}
        ok &= check(
            "create_shift with confirm posts",
            not err and body.get("title") == "Test shift",
            str(body),
        )
        before = len(server.requests)
        err, text = client.tool("delete_shift", {"schedulerId": "S1", "shiftId": "SH9"})
        sent = len(server.requests) - before
        ok &= check(
            "delete_shift refused without confirm",
            err and "confirm=true" in text and sent == 0,
            "sent=%d" % sent,
        )
        err, text = client.tool(
            "delete_shift", {"schedulerId": "S1", "shiftId": "SH9", "confirm": True}
        )
        ok &= check("delete_shift with confirm", not err, text[:120])
        err, text = client.tool("no_such_tool", {})
        ok &= check("unknown tool errors", err and "Unknown tool" in text, text[:120])
        err, text = client.tool("list_shifts", {})
        ok &= check(
            "missing required arg errors",
            err and "schedulerId" in text,
            text[:120],
        )
        err, text = client.tool("generate_upload_url", {"featureType": "chat"})
        ok &= check("generate_upload_url", not err and "uploadUrl" in text, text[:120])
        key_seen = any(
            r["method"] in ("GET", "POST", "DELETE") and not r["has_key"]
            for r in server.requests
        )
        ok &= check("api key header present on calls", not key_seen, "")
    finally:
        client.close()
        server.shutdown()
    return ok


def run_error_suite(mode, needle):
    server = start_mock(mode)
    base = "http://127.0.0.1:%d" % server.server_address[1]
    client = McpClient(base, TEST_KEY)
    ok = True
    try:
        err, text = client.tool("get_account", {})
        ok &= check(
            "%s maps to error" % mode,
            err and needle in text and TEST_KEY not in text,
            text[:160],
        )
    finally:
        client.close()
        server.shutdown()
    return ok


def run_no_key_suite():
    server = start_mock("ok")
    base = "http://127.0.0.1:%d" % server.server_address[1]
    client = McpClient(base, None)
    ok = True
    try:
        resp = client.call("tools/list")
        names = {t["name"] for t in resp["result"]["tools"]}
        ok &= check("tools/list works without key", names == EXPECTED_TOOLS, "")
        err, text = client.tool("get_account", {})
        ok &= check(
            "tools/call without key errors",
            err and "CONNECTEAM_API_KEY is not set" in text,
            text[:120],
        )
    finally:
        client.close()
        server.shutdown()
    return ok


def main():
    ok = True
    ok &= run_ok_suite()
    ok &= run_error_suite("401", "401")
    ok &= run_error_suite("429", "429")
    ok &= run_no_key_suite()
    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
