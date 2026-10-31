"""Real HTTP smoke test: the stdlib server on an ephemeral port must
serve all three OpenAI-compatible endpoints with the right shapes."""
import json
import threading
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer

from tesla_charge_oracle.config import Settings, VehicleConfig
from tesla_charge_oracle.server import make_handler
from tesla_charge_oracle.service import ChargeOracleService


def _start_server(**over):
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode="never", **over)
    service = ChargeOracleService(
        settings, now_fn=lambda: datetime(2026, 10, 31, 18, 0))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, method, path, payload=None, headers=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_http_surface():
    httpd, base = _start_server()
    try:
        status, body = _call(base, "GET", "/health")
        assert status == 200 and body["status"] == "ok"
        status, body = _call(base, "GET", "/v1/models")
        assert status == 200 and body["data"][0]["id"] == "tesla-charge-oracle"
        status, body = _call(base, "POST", "/v1/chat/completions", {
            "model": "tesla-charge-oracle",
            "messages": [{"role": "user",
                          "content": "cheapest way to 90% by 7am, currently at 40%"}]})
        assert status == 200
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert "90%" in body["choices"][0]["message"]["content"]
        status, body = _call(base, "POST", "/v1/embeddings",
                             {"input": "overnight charging"})
        assert status == 200 and len(body["data"][0]["embedding"]) == 384
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_bearer_auth_enforced():
    import urllib.error
    import urllib.request
    httpd, base = _start_server(server_api_key="secret123")
    try:
        with urllib.request.urlopen(base + "/v1/models") as _:
            raise AssertionError("unauthenticated request should fail")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    finally:
        httpd.shutdown()
        httpd.server_close()
