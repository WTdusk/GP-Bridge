"""Strict PDF-to-profile extraction through the OpenAI Responses API."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from preset_manager import validate_ai_profile


SYSTEM_INSTRUCTIONS = """You extract MIDI articulation mappings from official Kontakt instrument guides.
Only report mappings explicitly documented in the attached PDF. Never infer keyswitches,
MIDI note octave conventions, velocity layers, CC behavior, channels, or technique support.
If the guide does not establish a value, leave that mapping out and list the issue in
ambiguities or unsupported. Return one JSON object only, no markdown, with this shape:
{
  "schema_version": 1, "vendor": "", "library": "", "instrument": "",
  "kontakt_version": "unknown", "library_version": "unknown",
  "octave_convention": "C4=60 or unknown",
  "source": {"document": "", "pages": [1], "octave_convention": "", "confidence": "documented"},
  "default_channel": 1, "string_channels": {},
  "techniques": {"palm_mute": {"events": [{"type":"keyswitch","note":24,"velocity":127,"duration_ticks":1,"offset_ticks":-1}], "source_pages":[1], "evidence":"exact short source excerpt", "confidence":"documented", "velocity":{"factor":0.8,"offset":0,"min":1,"max":127}}},
  "combinations": [], "unsupported": [], "ambiguities": []
}
Every technique must cite source_pages and a short verbatim evidence quote. Supported event
types: keyswitch, cc, pitch_bend, program_change. For undocumented mappings do not create an
event. If no reliable mappings can be extracted, return {"extraction_failed":"reason"}.
"""


def extract_profile(pdf_path: str | Path, api_key: str, model: str, endpoint: str,
                    library: str = "", instrument: str = "") -> dict[str, Any]:
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf" or not path.is_file():
        raise ValueError("Select a readable PDF guide")
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("PDF is larger than the 50 MB request limit")
    if not api_key.strip():
        raise ValueError("Enter an OpenAI API key to run extraction")
    if not model.strip():
        raise ValueError("Enter a model that supports PDF inputs")
    url = endpoint.strip().rstrip("/")
    if not url:
        url = "https://api.openai.com/v1/responses"
    if not url.endswith("/responses"):
        url += "/responses"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    request_body = {
        "model": model.strip(),
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": [{"role": "user", "content": [
            {"type": "input_file", "filename": path.name, "file_data": f"data:application/pdf;base64,{encoded}"},
            {"type": "input_text", "text": f"The user identifies the library as {library!r} and the instrument/preset as {instrument!r}. Extract only explicit guitar/bass performance MIDI mappings from this official guide. Cite page numbers and short direct evidence for each technique. Return the required JSON."}
        ]}],
        "max_output_tokens": 8000
    }
    req = urllib.request.Request(url, data=json.dumps(request_body).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"AI extraction request failed (HTTP {exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach the AI service: {exc}") from exc
    output_text = payload.get("output_text")
    if not output_text:
        chunks = []
        for item in payload.get("output", []):
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    chunks.append(part.get("text", ""))
        output_text = "\n".join(chunks)
    try:
        result = json.loads(output_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("AI returned invalid JSON; no preset was created") from exc
    if not isinstance(result, dict):
        raise ValueError("AI returned a non-object JSON result; no preset was created")
    if result.get("extraction_failed"):
        raise ValueError(f"AI extraction failed: {result['extraction_failed']}")
    errors = validate_ai_profile(result)
    if errors:
        raise ValueError("AI extraction failed profile verification:\n" + "\n".join(errors))
    return result
