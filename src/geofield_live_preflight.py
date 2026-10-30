# -*- coding: utf-8 -*-
"""Read-only local GeoField server integration diagnosis.

Only three allowlisted loopback GET endpoints; never start CAD/FEA/ML jobs,
never call a paid LLM, and never print credentials, Python paths or user data.
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.error
import urllib.request

ENDPOINTS = {
    "server": "/api/status",
    "r12": "/api/ml/r12/preflight",
    "ai": "/api/integration/preflight",
}
MAX_SIZE = 65536


def fetch_status(port, endpoint):
    if endpoint not in ENDPOINTS.values() or not (1 <= port <= 65535):
        raise ValueError("Only known local, read-only endpoints are allowed")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:%d%s" % (port, endpoint), timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("HTTP status not OK")
        content = response.read(MAX_SIZE + 1)
        if len(content) > MAX_SIZE:
            raise ValueError("Response too large")
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Invalid server JSON")
    return result


def sanitize(results):
    """Never print the raw server response: it may contain file paths."""
    state = {"schema": "geofield-live-preflight-v1",
             "readonly": True, "paid_api_called": False, "ml_job_started": False,
             "server": {"reachable": False}, "r12": {"checked": False},
             "deepseek": {"checked": False}}
    server = results.get("server")
    if isinstance(server, dict):
        state["server"] = {"reachable": True, "ok": server.get("ok") is True}
    elif isinstance(server, Exception):
        state["server"]["error_type"] = type(server).__name__

    r12 = results.get("r12")
    if isinstance(r12, dict):
        state["r12"] = {"checked": True,
                        "available": r12.get("available") is True,
                        "missing_count": len(r12["missing"]) if isinstance(r12.get("missing"), list) else None,
                        "python_selected": bool(r12.get("python")),
                        "inference_performed": False}
    elif isinstance(r12, Exception):
        state["r12"]["error_type"] = type(r12).__name__

    ai = results.get("ai")
    config = ai.get("agent", {}).get("llm_config") if isinstance(ai, dict) and isinstance(ai.get("agent"), dict) else None
    if isinstance(config, dict):
        state["deepseek"] = {
            "checked": True, "configured_in_running_server": config.get("configured") is True,
            "provider": config.get("configured_provider") if config.get("configured_provider") in ("deepseek", "openai") else None,
            "model": config.get("selected_model") if isinstance(config.get("selected_model"), str) else None,
            "live_request_sent": False,
        }
    elif isinstance(ai, Exception):
        state["deepseek"]["error_type"] = type(ai).__name__
    else:
        state["deepseek"]["error_type"] = "llm_config_unavailable"
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8600)
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535):
        parser.error("Invalid port")
    results = {}
    for name, endpoint in ENDPOINTS.items():
        try:
            results[name] = fetch_status(args.port, endpoint)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            results[name] = exc
    print(json.dumps(sanitize(results), indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if isinstance(results.get("server"), dict) and results["server"].get("ok") is True else 10


if __name__ == "__main__":
    sys.exit(main())
