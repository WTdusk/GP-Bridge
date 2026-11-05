#!/usr/bin/env python3
"""Minimal stdio MCP server for GP Bridge.

It implements initialize, tools/list and tools/call using newline-delimited
JSON-RPC, which is sufficient for local Agent integrations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from gpbridge import convert, parse_gpx, track_names_from_config, write_midi
from preset_manager import default_preset_dir, list_presets, load_preset, validate_preset


def result(req_id, payload):
    return {"jsonrpc": "2.0", "id": req_id, "result": payload}


def error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


TOOLS = [
    {"name": "list_presets", "description": "List GP Bridge instrument profiles.", "inputSchema": {"type": "object", "properties": {"folder": {"type": "string"}}}},
    {"name": "inspect_score", "description": "Read Guitar Pro XML/GPX and return notes, tuning and techniques.", "inputSchema": {"type": "object", "required": ["input"], "properties": {"input": {"type": "string"}}}},
    {"name": "convert_score", "description": "Convert Guitar Pro XML/GPX using a profile into MIDI and a report.", "inputSchema": {"type": "object", "required": ["input", "output", "preset"], "properties": {"input": {"type": "string"}, "output": {"type": "string"}, "preset": {"type": "string"}, "strict": {"type": "boolean"}, "split_tracks": {"type": "boolean"}, "sustain_mode": {"type": "string", "enum": ["notated", "auto"]}}}},
]


def call_tool(name, args):
    if name == "list_presets":
        folder = args.get("folder") or str(default_preset_dir())
        return {"presets": [str(p) for p in list_presets(folder)]}
    if name == "inspect_score":
        score = parse_gpx(args["input"])
        return {"notes": len(score.notes), "tuning": score.tuning, "tempo": score.tempo, "techniques": sorted({t for n in score.notes for t in n.techniques}), "warnings": score.warnings, "source_tracks": [{"id": source, "name": next(n.source_track_name for n in score.notes if n.source_track == source), "notes": sum(n.source_track == source for n in score.notes)} for source in sorted({n.source_track for n in score.notes})]}
    if name == "convert_score":
        profile = load_preset(args["preset"])
        for key in ("split_tracks", "sustain_mode"):
            if key in args: profile[key] = args[key]
        errors = validate_preset(profile)
        if errors: raise ValueError("invalid preset: " + "; ".join(errors))
        score = parse_gpx(args["input"]); events, report = convert(score, profile)
        if args.get("strict", True) and any("unmapped technique" in w for w in report["warnings"]):
            raise ValueError("unmapped techniques: " + "; ".join(report["warnings"]))
        write_midi(events, args["output"], score.tempo, track_names_from_config(profile), bool(profile.get("split_tracks", True)))
        report_path = Path(args["output"]).with_suffix(".report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"output": str(args["output"]), "report": str(report_path), "summary": report}
    raise ValueError(f"unknown tool: {name}")


def main():
    # MCP stdio is UTF-8 regardless of the Windows console code page.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        try:
            req = json.loads(line)
        except (ValueError, UnicodeError) as exc:
            sys.stdout.write(json.dumps(error(None, -32700, str(exc))) + "\n"); sys.stdout.flush()
            continue
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"), str):
            sys.stdout.write(json.dumps(error(req.get("id") if isinstance(req, dict) else None, -32600, "invalid request")) + "\n"); sys.stdout.flush()
            continue
        # Notifications never receive responses, including unknown ones.
        if "id" not in req:
            continue
        req_id = req["id"]
        try:
            method = req["method"]
            if method == "initialize":
                response = result(req_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "gpbridge", "version": "0.1.0"}})
            elif method == "ping":
                response = result(req_id, {})
            elif method == "tools/list":
                response = result(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = req.get("params", {})
                if not isinstance(params, dict) or params.get("name") not in [tool["name"] for tool in TOOLS] or not isinstance(params.get("arguments", {}), dict):
                    response = error(req_id, -32602, "invalid tool name or arguments")
                else:
                    try:
                        data = call_tool(params["name"], params.get("arguments", {}))
                        response = result(req_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}], "structuredContent": data})
                    except Exception as exc:
                        response = result(req_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
            else:
                response = error(req_id, -32601, f"method not found: {method}")
        except Exception as exc:
            response = error(req_id, -32603, str(exc))
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n"); sys.stdout.flush()


if __name__ == "__main__":
    main()
