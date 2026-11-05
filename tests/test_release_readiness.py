import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gpbridge import NoteEvent, Score, convert, parse_gpx
from preset_manager import validate_ai_profile, validate_preset


@pytest.mark.parametrize("profile", [
    [], {"techniques": []}, {"string_channels": []}, {"combinations": None},
    {"default_channel": "oops"}, {"string_channels": {"1": None}},
    {"default_channel": 1.5}, {"default_channel": True},
    {"default_channel": "1.0"}, {"sustain_mode": []},
    {"techniques": {"x": {"velocity": {"factor": "oops"}}}},
    {"techniques": {"x": {"velocity": {"factor": float("nan")}}}},
    {"techniques": {"x": {"events": [{"duration_ticks": -1}]}}},
    {"split_tracks": "false"}, {"combinations": [{"when": [[]]}]},
])
def test_invalid_profiles_report_errors_without_crashing(profile):
    assert validate_preset(profile)
    assert validate_ai_profile(profile)


def test_matched_combo_preserves_unrelated_standalone_mapping():
    score = Score([NoteEvent(0, 480, 1, 0, techniques=["palm_mute", "vibrato"], pitch=64)], {1: 64})
    profile = {
        "default_channel": 1,
        "techniques": {"vibrato": {"events": [{"type": "cc", "controller": 1, "value": 99}]}},
        "combinations": [
            {"when": ["palm_mute"], "events": []},
            {"when": ["vibrato", "slide"], "events": []},
        ],
    }
    events, report = convert(score, profile)
    assert (0, bytes([0xb0, 1, 99])) in events
    assert not report["warnings"]


def test_timewise_musicxml_rejected_before_incorrect_conversion(tmp_path):
    source = tmp_path / "timewise.xml"
    source.write_text("<score-timewise><measure><part id='P1'><note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration></note></part></measure></score-timewise>")
    with pytest.raises(ValueError, match="score-partwise"):
        parse_gpx(source)


def test_cli_rejects_bad_mapping_before_writing_midi(tmp_path):
    source = tmp_path / "map.json"
    source.write_text('{"default_channel": "bad"}')
    output = tmp_path / "out.mid"
    proc = subprocess.run([sys.executable, "gpbridge.py", "examples/drop_d.gpx", "-c", str(source), "-o", str(output)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "invalid preset" in proc.stderr
    assert not output.exists()


def test_mcp_utf8_notifications_errors_and_recovery(tmp_path):
    folder = tmp_path / "中文预设"
    folder.mkdir()
    (folder / "吉他.json").write_text('{}')
    messages = [
        '{broken', '[]',
        json.dumps({"jsonrpc": "2.0", "method": "notifications/unknown"}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_presets", "arguments": {"folder": str(folder)}}}, ensure_ascii=False),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "inspect_score", "arguments": {"input": str(tmp_path / "missing.gpx")}}}),
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "unknown"}}),
        json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/list"}),
    ]
    proc = subprocess.run([sys.executable, "mcp_server.py"], input=("\n".join(messages) + "\n").encode("utf-8"), capture_output=True, env={**os.environ, "PYTHONIOENCODING": "ascii"})
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines()]
    assert len(replies) == 7
    assert replies[0]["error"]["code"] == -32700
    assert replies[1]["error"]["code"] == -32600
    assert replies[2] == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert replies[3]["result"]["structuredContent"]["presets"] == [str(folder / "吉他.json")]
    assert replies[4]["result"]["isError"] is True
    assert replies[5]["error"]["code"] == -32602
    assert len(replies[6]["result"]["tools"]) == 3
