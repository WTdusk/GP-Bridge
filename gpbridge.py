#!/usr/bin/env python3
"""Guitar Pro XML/GPX to VST-oriented MIDI converter.

The parser is deliberately tolerant: Guitar Pro XML versions have moved
fields around over time, so values are found by local tag names and common
attribute names rather than one rigid schema.
"""
from __future__ import annotations

import argparse
import bz2
import json
import logging
import lzma
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PPQ = 480
STANDARD_GUITAR = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40, 7: 35, 8: 30}
STANDARD_BASS = {1: 43, 2: 38, 3: 33, 4: 28, 5: 23, 6: 18}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def descendants(el: ET.Element, name: str) -> list[ET.Element]:
    return [x for x in el.iter() if local(x.tag) == name.lower()]


def first_text(el: ET.Element, names: Iterable[str], default: str | None = None) -> str | None:
    wanted = {n.lower() for n in names}
    for x in el.iter():
        if local(x.tag) in wanted and x.text and x.text.strip():
            return x.text.strip()
    return default


def number(el: ET.Element, names: Iterable[str], default: int | None = None) -> int | None:
    wanted = {n.lower() for n in names}
    for x in el.iter():
        if local(x.tag) in wanted:
            value = x.text or next((v for k, v in x.attrib.items() if k.lower() in {"value", "number", "n"}), "")
            try:
                return int(float(value.strip()))
            except (ValueError, AttributeError):
                pass
    return default


@dataclass
class NoteEvent:
    tick: int
    duration: int
    string: int
    fret: int
    velocity: int = 100
    techniques: list[str] = field(default_factory=list)
    pitch: int = 60
    bend_points: list[tuple[int, int]] = field(default_factory=list)
    source_track: int = 1
    source_track_name: str = ""
    tie_start: bool = False
    tie_stop: bool = False


@dataclass
class Score:
    notes: list[NoteEvent]
    tuning: dict[int, int]
    tempo: int = 120
    warnings: list[str] = field(default_factory=list)
    track_tunings: dict[int, dict[int, int]] = field(default_factory=dict)
    track_ends: dict[int, int] = field(default_factory=dict)


TECHNIQUE_ALIASES = {
    "palmmute": "palm_mute", "muted": "palm_mute", "deadnote": "palm_mute", "dead": "palm_mute",
    "harmonic": "artificial_harmonic", "naturalharmonic": "natural_harmonic", "artificialharmonic": "artificial_harmonic",
    "bend": "bend", "slide": "slide", "glissando": "slide", "hammeron": "hammer_on",
    "hammer": "hammer_on", "pulloff": "pull_off", "pull": "pull_off", "vibrato": "vibrato",
    "tremolo": "tremolo", "staccato": "staccato", "tapping": "tapping", "tap": "tapping",
    "let_ring": "let_ring", "letring": "let_ring", "sustain": "let_ring", "tie": "tie",
    "arpeggio": "strum", "arpeggiate": "strum",
    "strum": "strum", "downstroke": "strum", "upstroke": "strum",
}


def _techniques(note: ET.Element) -> list[str]:
    result: list[str] = []
    for x in note.iter():
        tag = local(x.tag).replace("_", "")
        text = (x.text or "").strip().lower().replace(" ", "")
        active = text in {"true", "1", "yes"} or x.attrib.get("enabled", "").lower() in {"true", "1"}
        if tag == "harmonic":
            harmonic_type = " ".join([
                *(value.lower() for key, value in x.attrib.items() if key.lower() in {"type", "kind", "harmonictype"}),
                *((child.text or "").strip().lower() for child in x.iter() if local(child.tag) in {"type", "kind", "harmonictype"}),
            ])
            if "artificial" in harmonic_type or "pinch" in harmonic_type:
                if "artificial_harmonic" not in result:
                    result.append("artificial_harmonic")
                continue
            if "natural" in harmonic_type:
                if "natural_harmonic" not in result:
                    result.append("natural_harmonic")
                continue
            # Guitar Pro's generic harmonic marker does not carry enough
            # information to distinguish the two Shreddage harmonic modes.
            # The profile policy is to use Artificial Harmonics as the
            # deterministic default instead of silently dropping the marker.
            if "artificial_harmonic" not in result:
                result.append("artificial_harmonic")
            continue
        key = TECHNIQUE_ALIASES.get(tag) or TECHNIQUE_ALIASES.get(text)
        if key and (active or text == "" or tag in {"bend", "slide", "vibrato", "harmonic"}):
            if key not in result:
                result.append(key)
    # A number of GPX files use technique names as element text.
    for text in ((x.text or "") for x in note.iter()):
        key = TECHNIQUE_ALIASES.get(text.strip().lower().replace(" ", ""))
        if key and key not in result:
            result.append(key)
    return result


def _bend_points(note: ET.Element) -> list[tuple[int, int]]:
    """Read common GPX/GPIF bend point layouts as (position, value) pairs.

    Guitar Pro exports have used both child elements and attributes. Position is
    kept in the source unit and normalized later when rendering the pitch wheel.
    """
    points: list[tuple[int, int]] = []
    for point in note.iter():
        tag = local(point.tag).replace("_", "")
        if tag not in {"bendpoint", "point", "bendvalue"}:
            continue

        def read(names: set[str]) -> int | None:
            for key, value in point.attrib.items():
                if key.lower().replace("_", "") in names:
                    try:
                        return int(float(value))
                    except (TypeError, ValueError):
                        pass
            for child in point:
                if local(child.tag).replace("_", "") in names and child.text:
                    try:
                        return int(float(child.text.strip()))
                    except (TypeError, ValueError):
                        pass
            return None

        position = read({"position", "pos", "time", "offset", "tick"})
        value = read({"value", "bend", "amount", "semitones", "pitch"})
        if position is not None and value is not None:
            points.append((position, value))

    if points:
        return sorted(set(points))

    # Some exports place a flat sequence under <Bend>: Position, Value, ...
    bend_nodes = [child for child in note.iter() if local(child.tag) == "bend"]
    for bend in bend_nodes:
        children = list(bend)
        for index in range(0, len(children) - 1, 2):
            left, right = children[index], children[index + 1]
            if local(left.tag) == "position" and local(right.tag) in {"value", "bend"}:
                try:
                    points.append((int(float((left.text or "0").strip())), int(float((right.text or "0").strip()))))
                except ValueError:
                    continue
    return sorted(set(points))


def _duration_ticks(beat: ET.Element) -> int:
    value = first_text(beat, ["value", "duration", "denominator"])
    if value:
        v = value.lower()
        names = {"whole": 1920, "half": 960, "quarter": 480, "eighth": 240, "sixteenth": 120, "thirtysecond": 60}
        if v in names:
            return names[v]
        try:
            # GPX commonly stores denominator (4 = quarter, 8 = eighth).
            return int(PPQ * 4 / float(v))
        except ValueError:
            pass
    return PPQ


def _midi_pitch(note: ET.Element) -> int | None:
    pitch = next((x for x in note if local(x.tag) == "pitch"), None)
    if pitch is None:
        return None
    step = first_text(pitch, ["step"])
    octave = number(pitch, ["octave"])
    alter = number(pitch, ["alter"], 0) or 0
    if not step or octave is None:
        return None
    offsets = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
    if step.lower() not in offsets:
        return None
    return 12 * (octave + 1) + offsets[step.lower()] + alter


def _musicxml_techniques(note: ET.Element) -> list[str]:
    result: list[str] = []
    for node in note.iter():
        tag = local(node.tag).replace("_", "").replace("-", "")
        text = (node.text or "").strip().lower().replace("-", "").replace(" ", "")
        if tag in {"hammeron", "hammer"} or text in {"hammeron", "hammer"}:
            if "hammer_on" not in result:
                result.append("hammer_on")
        elif tag in {"pulloff", "pull"} or text in {"pulloff", "pull"}:
            if "pull_off" not in result:
                result.append("pull_off")
        elif tag in {"slide", "glissando"} or text in {"slide", "glissando"}:
            # MusicXML writes both ends of a slide. The keyswitch belongs on
            # the source note, so do not duplicate it on the stop note.
            if str(node.attrib.get("type", "start")).lower() != "stop" and "slide" not in result:
                result.append("slide")
        elif tag == "bend" or text == "bend":
            if "bend" not in result:
                result.append("bend")
        elif tag == "vibrato" or text == "vibrato":
            if "vibrato" not in result:
                result.append("vibrato")
        elif tag == "tremolo" or text == "tremolo":
            if "tremolo" not in result:
                result.append("tremolo")
        elif tag in {"tap", "tapping"} or text in {"tap", "tapping"}:
            if "tapping" not in result:
                result.append("tapping")
        elif tag in {"arpeggiate", "strum", "downbow", "upbow"} or text in {"arpeggiate", "strum", "downbow", "upbow"}:
            if "strum" not in result:
                result.append("strum")
        elif tag in {"palmmute", "muted", "deadnote", "mute"} or text in {"palmmute", "muted", "deadnote", "mute"}:
            if "palm_mute" not in result:
                result.append("palm_mute")
        elif tag in {"staccato", "staccatissimo"} or text in {"staccato", "staccatissimo"}:
            if "staccato" not in result:
                result.append("staccato")
        elif tag == "letring" or text in {"letring", "let_ring"}:
            if "let_ring" not in result:
                result.append("let_ring")
        elif tag in {"harmonic", "naturalharmonic", "artificialharmonic"} or text in {"harmonic", "naturalharmonic", "artificialharmonic"}:
            if "natural" in text or tag == "naturalharmonic" or any(local(x.tag) == "natural" for x in node):
                key = "natural_harmonic"
            else:
                key = "artificial_harmonic"
            if key not in result:
                result.append(key)
    return result


def _musicxml_velocity(note: ET.Element) -> int:
    value = number(note, ["velocity", "vel"])
    if value is not None:
        return max(1, min(127, value))
    dynamics = {"pppp": 24, "ppp": 32, "pp": 45, "p": 58, "mp": 72,
                "mf": 86, "f": 100, "ff": 112, "fff": 120, "ffff": 127}
    for node in note.iter():
        tag = local(node.tag)
        if tag in dynamics:
            return dynamics[tag]
        if tag == "dynamics":
            for child in node:
                if local(child.tag) in dynamics:
                    return dynamics[local(child.tag)]
    return 100


def _infer_string_for_pitch(pitch: int, tuning: dict[int, int], max_fret: int = 24) -> int:
    """Choose a practical string for standard-tuned notation without TAB data."""
    candidates = []
    for string, open_pitch in tuning.items():
        fret = pitch - open_pitch
        if 0 <= fret <= max_fret:
            candidates.append((fret, -string, string))
    if not candidates:
        return 0
    return min(candidates)[2]


def parse_musicxml(path: str | Path, root: ET.Element | None = None) -> Score:
    source = Path(path)
    root = root if root is not None else ET.parse(source).getroot()
    tuning = dict(STANDARD_GUITAR)
    has_nonstandard_tuning = False
    warnings: list[str] = []
    notes: list[NoteEvent] = []
    tempo = number(root, ["per-minute", "tempo", "bpm"], 120) or 120
    parts = [x for x in root if local(x.tag) == "part"]
    if not parts:
        parts = [root]

    # MusicXML time is measured in divisions per quarter. backup/forward
    # restore the cursor for voices and chords instead of flattening all
    # notes onto the first beat.
    track_tunings, track_ends = {}, {}
    part_names = {x.get("id"): first_text(x, ["part-name"], "") for x in root.iter() if local(x.tag) == "score-part"}
    for track_index, part in enumerate(parts, 1):
        tuning = {i: STANDARD_GUITAR[i] for i in range(1, 7)}
        has_nonstandard_tuning = False
        absolute_measure_tick = 0
        divisions = 1
        for measure in [x for x in part.iter() if local(x.tag) == "measure"]:
            cursor = 0
            max_cursor = 0
            last_note_start = 0
            last_duration = 0
            for child in list(measure):
                tag = local(child.tag)
                if tag == "attributes":
                    divisions = number(child, ["divisions"], divisions) or divisions
                    for string_node in [x for x in child.iter() if local(x.tag) == "staff-tuning"]:
                        line = number(string_node, ["line", "number"])
                        if line is None:
                            try:
                                line = int(string_node.attrib.get("line", string_node.attrib.get("number", "0")))
                            except (TypeError, ValueError):
                                line = None
                        step = first_text(string_node, ["tuning-step"])
                        octave = number(string_node, ["tuning-octave"])
                        alter = number(string_node, ["tuning-alter"], 0) or 0
                        if line and step and octave is not None:
                            # MusicXML staff lines count from bottom to top;
                            # TAB string numbers count from high to low.
                            string_number = (number(child, ["staff-lines"], 6) or 6) + 1 - line
                            tuning[string_number] = 12 * (octave + 1) + {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}.get(step.lower(), 0) + alter
                            if string_number in STANDARD_GUITAR and tuning[string_number] != STANDARD_GUITAR[string_number]:
                                has_nonstandard_tuning = True
                elif tag in {"backup", "forward"}:
                    amount = number(child, ["duration"], 0) or 0
                    cursor += amount if tag == "forward" else -amount
                    cursor = max(0, cursor)
                elif tag == "sound":
                    tempo = number(child, ["tempo"], tempo) or tempo
                elif tag == "note":
                    duration_units = number(child, ["duration"], 0) or 0
                    duration = max(1, round(PPQ * duration_units / max(1, divisions)))
                    is_chord = any(local(x.tag) == "chord" for x in child)
                    start_units = last_note_start if is_chord else cursor
                    if not any(local(x.tag) == "rest" for x in child):
                        pitch = _midi_pitch(child)
                        if pitch is None:
                            warnings.append(f"MusicXML note at tick {absolute_measure_tick + round(start_units * PPQ / divisions)} has no pitch")
                        else:
                            explicit_string = number(child, ["string", "stringnumber"], 0) or 0
                            if explicit_string:
                                string = explicit_string
                            elif has_nonstandard_tuning:
                                # With non-standard tuning and no TAB string,
                                # preserve the written pitch and avoid a false
                                # per-string channel assignment.
                                string = 0
                            else:
                                string = _infer_string_for_pitch(pitch, tuning)
                            fret = number(child, ["fret", "fretvalue"], 0) or 0
                            note_tick = absolute_measure_tick + round(start_units * PPQ / divisions)
                            techniques = _musicxml_techniques(child)
                            ties = [x for x in child.iter() if local(x.tag) in {"tie", "tied"}]
                            bends = [x for x in child.iter() if local(x.tag) == "bend"]
                            bend_points = []
                            if bends:
                                height = round(float(first_text(bends[0], ["bend-alter"], "0")) * 50)
                                pre = any(local(x.tag) == "pre-bend" for x in bends[0])
                                release = any(local(x.tag) == "release" for x in bends[0])
                                bend_points = [(0, height if pre else 0), (60, 0 if release else height)]
                            notes.append(NoteEvent(note_tick, duration, string, fret,
                                                   _musicxml_velocity(child), techniques, pitch, bend_points,
                                                   track_index, part_names.get(part.get("id"), "") or f"Guitar {track_index}",
                                                   any(x.get("type") == "start" for x in ties),
                                                   any(x.get("type") == "stop" for x in ties)))
                    if not is_chord:
                        last_note_start = cursor
                        last_duration = duration_units
                        cursor += duration_units
                    max_cursor = max(max_cursor, cursor, start_units + duration_units)
            measure_ticks = round(max_cursor * PPQ / max(1, divisions))
            absolute_measure_tick += measure_ticks
        track_tunings[track_index] = dict(tuning)
        track_ends[track_index] = absolute_measure_tick
    if not notes:
        warnings.append("no pitched MusicXML notes were found")
    notes = _merge_ties(notes, warnings)
    return Score(notes, track_tunings.get(1, tuning), tempo, warnings, track_tunings, track_ends)


def _parse_gp_xml(path: str | Path, root: ET.Element | None = None) -> Score:
    source = Path(path)
    root = root if root is not None else ET.parse(source).getroot()
    tuning = dict(STANDARD_GUITAR)
    warnings: list[str] = []
    tempo = number(root, ["tempo", "bpm"], 120) or 120
    notes: list[NoteEvent] = []
    # A GPIF score contains one beat sequence per source track. Parsing all
    # Beat descendants globally flattens two guitars into one timeline.
    source_tracks = [x for x in root.iter() if local(x.tag) == "track"]
    if not source_tracks:
        source_tracks = [root]
    track_tunings, track_ends = {}, {}
    for track_index, track in enumerate(source_tracks, 1):
        tuning = dict(STANDARD_GUITAR)
        for s in [x for x in track.iter() if local(x.tag) == "string"]:
            idx = number(s, ["number", "index", "string"])
            if idx is None:
                idx = int(s.get("number", s.get("index", "0")))
            pitch = number(s, ["pitch", "midi", "value"])
            if idx and pitch is not None:
                tuning[idx] = pitch
        tick = 0
        track_name = first_text(track, ["name", "trackname", "instrument"], "") or ""
        beats = [x for x in track.iter() if local(x.tag) == "beat"]
        if not beats:
            beats = [root] if track is root else []
        for beat in beats:
            duration = _duration_ticks(beat)
            note_nodes = [x for x in beat.iter() if local(x.tag) == "note"]
            for note in note_nodes:
                string = number(note, ["string", "stringnumber"], 1) or 1
                fret = number(note, ["fret", "fretvalue"], 0) or 0
                velocity = number(note, ["velocity", "dynamic", "vel"], 100) or 100
                velocity = max(1, min(127, velocity))
                techniques = _techniques(note)
                bend_points = _bend_points(note)
                if bend_points and "bend" not in techniques:
                    techniques.append("bend")
                if string not in tuning:
                    warnings.append(f"string {string} has no tuning; using MIDI 40")
                pitch = tuning.get(string, 40) + fret
                notes.append(NoteEvent(tick, duration, string, fret, velocity, techniques,
                                       pitch, bend_points, track_index, track_name))
            tick += duration
        track_tunings[track_index] = dict(tuning)
        track_ends[track_index] = tick
    notes = _merge_ties(notes, warnings)
    if not notes:
        warnings.append("no Note elements were found")
    return Score(notes, track_tunings.get(1, tuning), tempo, warnings, track_tunings, track_ends)


def _extend_sustains(notes: list[NoteEvent]) -> None:
    """Carry let-ring and tied notes to the next note on the same source string."""
    grouped: dict[tuple[int, int], list[NoteEvent]] = {}
    for note in notes:
        grouped.setdefault((note.source_track, note.string), []).append(note)
    for group in grouped.values():
        group.sort(key=lambda item: item.tick)
        for index, note in enumerate(group):
            if not ({"let_ring", "tie"} & set(note.techniques)):
                continue
            next_note = group[index + 1] if index + 1 < len(group) else None
            if next_note is None:
                continue
            target_end = max(note.tick + note.duration, next_note.tick)
            note.duration = target_end - note.tick


def _merge_ties(notes: list[NoteEvent], warnings: list[str]) -> list[NoteEvent]:
    result, active = [], {}
    for note in sorted(notes, key=lambda n: n.tick):
        key = (note.source_track, note.string, note.pitch)
        previous = active.get(key)
        if note.tie_stop and previous is not None and previous.tick + previous.duration >= note.tick:
            previous.duration = max(previous.duration, note.tick + note.duration - previous.tick)
            previous.tie_start = note.tie_start
            if not note.tie_start:
                active.pop(key, None)
            continue
        if note.tie_stop:
            warnings.append(f"tie destination at tick {note.tick} has no matching source")
        result.append(note)
        if note.tie_start:
            active[key] = note
        else:
            active.pop(key, None)
    return result


def parse_gpx(path: str | Path) -> Score:
    """Parse GPIF/XML GPX and MusicXML with format-aware dispatch."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            candidates = [n for n in archive.namelist() if n.lower().endswith((".xml", ".gpif"))]
            if not candidates:
                raise ValueError(f"{source.name} is a ZIP GPX but contains no XML/GPIF score")
            preferred = next((n for n in candidates if "score" in n.lower() or "content" in n.lower() or "gpif" in n.lower()), candidates[0])
            try:
                root = ET.fromstring(archive.read(preferred))
            except ET.ParseError as exc:
                raise ValueError(f"GPX archive entry '{preferred}' is not valid XML: {exc}") from exc
    else:
        raw = source.read_bytes()
        if raw.startswith(b"PK"):
            raise ValueError(f"{source.name} looks like a damaged ZIP GPX and cannot be opened")
        if raw.startswith((b"BCFZ", b"BCFS")):
            from gpx_container import extract_gpif
            raw = extract_gpif(raw)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            # Some older GPX writers wrap the XML in a compressed stream
            # rather than a ZIP container. Try standard compression headers
            # and small offsets before reporting the file as proprietary.
            decompressed: bytes | None = None
            for offset in range(min(64, len(raw))):
                payload = raw[offset:]
                for decoder in (zlib.decompress, bz2.decompress, lzma.decompress):
                    try:
                        candidate = decoder(payload)
                    except Exception:
                        continue
                    if candidate.lstrip().startswith(b"<") or candidate.startswith(b"PK"):
                        decompressed = candidate
                        break
                if decompressed is not None:
                    break
            if decompressed is not None:
                if decompressed.startswith(b"PK"):
                    import io
                    with zipfile.ZipFile(io.BytesIO(decompressed)) as archive:
                        candidates = [n for n in archive.namelist() if n.lower().endswith((".xml", ".gpif"))]
                        if not candidates:
                            raise ValueError(f"{source.name} compressed GPX contains no XML/GPIF score")
                        preferred = next((n for n in candidates if "score" in n.lower() or "content" in n.lower() or "gpif" in n.lower()), candidates[0])
                        root = ET.fromstring(archive.read(preferred))
                else:
                    root = ET.fromstring(decompressed)
            else:
                header = raw[:8].hex(" ")
                raise ValueError(
                    f"无法解析 {source.name}：它不是 GPIF/XML。文件头为 {header}。"
                    "当前支持 ZIP GPX、GPIF/XML 和 MusicXML；请从 Guitar Pro 导出 GPIF/XML，"
                    "或使用 Guitar Pro 7/8 保存的 ZIP GPX。"
                ) from exc
    root_name = local(root.tag).replace("-", "").replace("_", "")
    if root_name == "scoretimewise":
        raise ValueError("MusicXML score-timewise is not supported; export score-partwise MusicXML instead")
    if root_name == "scorepartwise":
        return parse_musicxml(source, root)
    if root_name == "gpif" and any(local(x.tag) == "masterbars" for x in root):
        from gpif_reader import read_gpif
        return read_gpif(root)
    return _parse_gp_xml(source, root)


def _vlq(value: int) -> bytes:
    value = max(0, value)
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _midi_track(events: list[tuple[int, bytes]], tempo: int | None = None, name: str | None = None) -> bytes:
    events = sorted(((max(0, tick), data) for tick, data in events), key=lambda x: x[0])
    track = bytearray()
    if name:
        encoded = name.encode("utf-8")
        track += b"\x00\xff\x03" + _vlq(len(encoded)) + encoded
    if tempo is not None:
        mpqn = round(60_000_000 / max(1, tempo))
        track += b"\x00\xff\x51\x03" + mpqn.to_bytes(3, "big")
    previous = 0
    for tick, data in events:
        track += _vlq(tick - previous) + data
        previous = tick
    track += b"\x00\xff\x2f\x00"
    return bytes(track)


def write_midi(events: list[tuple[int, bytes]], path: str | Path, tempo: int = 120,
               track_names: dict[int, str] | None = None,
               split_tracks: bool = True) -> None:
    """Write MIDI, optionally grouping events by MIDI channel into tracks."""
    parts = getattr(events, "parts", {})
    if parts:
        if len(parts) > 128:
            raise ValueError("A MIDI file supports at most 128 source-instrument ports")
        tracks = [_midi_track([], tempo, "GP Bridge Tempo")]
        for port, (source, part) in enumerate(sorted(parts.items())):
            label, part_events = part
            groups = {}
            for tick, message in part_events:
                channel = message[0] & 15 if split_tracks else -1
                groups.setdefault(channel, []).append((tick, message))
            for channel, group in sorted(groups.items()):
                suffix = (track_names or {}).get(channel, f"Ch {channel + 1}" if channel >= 0 else "Combined")
                name = f"Part {source:02d} · {label} | {suffix}"
                track = _midi_track(group, None, name)
                # Each original instrument has its own MIDI port, retaining
                # the profile's string-channel assignments within that port.
                body = b"\x00\xff\x21\x01" + bytes([port]) + track
                tracks.append(body)
        if len(parts) == 1 and not split_tracks:
            source, (label, group) = next(iter(parts.items()))
            tracks = [_midi_track(group, tempo, f"Part {source:02d} · {label}")]
        header = b"MThd" + struct.pack(">IHHH", 6, int(len(tracks) > 1), len(tracks), PPQ)
        Path(path).write_bytes(header + b"".join(b"MTrk" + struct.pack(">I", len(track)) + track for track in tracks))
        return
    if not split_tracks:
        track = _midi_track(events, tempo, (track_names or {}).get(-1, "GP Bridge"))
        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ)
        Path(path).write_bytes(header + b"MTrk" + struct.pack(">I", len(track)) + track)
        return
    by_channel: dict[int, list[tuple[int, bytes]]] = {}
    for tick, data in events:
        channel = data[0] & 0x0F if data and (data[0] & 0xF0) not in {0xF0} else 0
        by_channel.setdefault(channel, []).append((tick, data))
    channels = sorted(by_channel)
    tracks = [_midi_track([], tempo, "GP Bridge Tempo")]
    for channel in channels:
        name = (track_names or {}).get(channel, f"MIDI Channel {channel + 1}")
        tracks.append(_midi_track(by_channel[channel], None, name))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
    payload = bytearray(header)
    for track in tracks:
        payload += b"MTrk" + struct.pack(">I", len(track)) + track
    Path(path).write_bytes(payload)


def track_names_from_config(config: dict[str, Any]) -> dict[int, str]:
    names: dict[int, str] = {}
    prefix = str(config.get("track_name_prefix") or "").strip()
    if not prefix:
        library = str(config.get("library") or "").strip()
        instrument = str(config.get("instrument") or config.get("preset_name") or "").strip()
        prefix = " / ".join(x for x in (library, instrument) if x)
    prefix = prefix or "GP Bridge"
    for string, channel in config.get("string_channels", {}).items():
        try:
            string_number = int(string)
            base_channel = int(channel)
            names[base_channel - 1] = f"{prefix} | String {string_number} | Ch {base_channel}"
        except (TypeError, ValueError):
            continue
    try:
        unassigned = int(config.get("unassigned_channel", 16))
        strum = int(config.get("strum_channel", 15))
        names[unassigned - 1] = f"{prefix} | Unassigned Pitch | Ch {unassigned}"
        names[strum - 1] = f"{prefix} | Strum / Arpeggio | Ch {strum}"
        names[-1] = f"{prefix} | Combined"
    except (TypeError, ValueError):
        pass
    return names


def _event_from_rule(rule: dict[str, Any], channel: int, tick: int, warnings: list[str],
                     note_duration: int = 0) -> list[tuple[int, bytes]]:
    kind = rule.get("type", "keyswitch").lower()
    offset = int(rule.get("offset_ticks", 0))
    when = max(0, tick + offset)
    if kind in {"keyswitch", "note"}:
        note = int(rule.get("note", 0)); velocity = int(rule.get("velocity", 127))
        length = int(rule.get("duration_ticks", 1))
        return [(when, bytes([0x90 | channel, note & 127, velocity & 127])),
                (when + length, bytes([0x80 | channel, note & 127, 0]))]
    if kind == "cc":
        controller = int(rule.get("controller", 1)) & 127
        events = [(when, bytes([0xB0 | channel, controller, int(rule.get("value", 127)) & 127]))]
        if rule.get("reset_at_note_off"):
            reset_tick = tick + max(0, note_duration)
            events.append((reset_tick, bytes([0xB0 | channel, controller, int(rule.get("reset_value", 0)) & 127])))
        return events
    if kind in {"pitch_bend", "pitchbend"}:
        value = int(rule.get("value", 8192))
        value = max(0, min(16383, value))
        return [(when, bytes([0xE0 | channel, value & 127, (value >> 7) & 127]))]
    if kind == "program_change":
        return [(when, bytes([0xC0 | channel, int(rule.get("program", 0)) & 127]))]
    warnings.append(f"unknown mapping event type: {kind}")
    return []


def _legato_durations(score: Score, config: dict[str, Any], warnings: list[str]) -> tuple[dict[int, int], list[dict[str, int]]]:
    durations = {id(note): max(0, note.duration) for note in score.notes}
    overlap = max(0, min(480, int(config.get("legato_overlap_ticks", 0))))
    slide_overlap = max(0, min(960, int(config.get("slide_overlap_ticks", 120))))
    max_interval = max(1, int(config.get("legato_max_interval_semitones", 12)))
    previous_by_string: dict[tuple[int, int], NoteEvent] = {}
    generated: list[dict[str, int]] = []

    for note in sorted(score.notes, key=lambda item: item.tick):
        key = (note.source_track, note.string)
        previous = previous_by_string.get(key)
        legato = "hammer_on" if "hammer_on" in note.techniques else "pull_off" if "pull_off" in note.techniques else None
        if legato:
            interval = note.pitch - previous.pitch if previous else 0
            correct_direction = interval > 0 if legato == "hammer_on" else interval < 0
            if previous is None or previous.tick >= note.tick:
                warnings.append(f"{legato} at tick {note.tick} has no earlier note on string {note.string}")
            elif not correct_direction or abs(interval) > max_interval:
                warnings.append(f"{legato} at tick {note.tick} cannot use same-string legato for interval {interval} semitones")
            else:
                target_end = note.tick + overlap
                old_end = previous.tick + durations[id(previous)]
                if target_end > old_end:
                    durations[id(previous)] = target_end - previous.tick
                generated.append({"string": note.string, "from_tick": previous.tick, "to_tick": note.tick,
                                  "overlap_ticks": max(0, previous.tick + durations[id(previous)] - note.tick)})
        previous_by_string[key] = note

    # Shreddage's slide transition needs a real overlap on both sides of the
    # transition. Extend the preceding note into the slide note and the slide
    # note into the following note, using a larger independent overlap.
    ordered = sorted(score.notes, key=lambda item: item.tick)
    for index, note in enumerate(ordered):
        if "slide" not in note.techniques:
            continue
        same_string_before = next((ordered[j] for j in range(index - 1, -1, -1) if ordered[j].string == note.string and ordered[j].source_track == note.source_track), None)
        same_string_after = next((ordered[j] for j in range(index + 1, len(ordered)) if ordered[j].string == note.string and ordered[j].source_track == note.source_track), None)
        if same_string_before is not None:
            end = note.tick + slide_overlap
            durations[id(same_string_before)] = max(durations[id(same_string_before)], end - same_string_before.tick)
        if same_string_after is not None:
            end = same_string_after.tick + slide_overlap
            durations[id(note)] = max(durations[id(note)], end - note.tick)
            # GP/MusicXML often marks the departure note. Keep the arrival
            # note overlapping its successor as well, for the transition tail.
            successor = next((candidate for candidate in ordered if candidate.tick > same_string_after.tick
                              and candidate.string == note.string and candidate.source_track == note.source_track), None)
            if successor is not None:
                durations[id(same_string_after)] = max(durations[id(same_string_after)], successor.tick + slide_overlap - same_string_after.tick)
        generated.append({"string": note.string, "from_tick": note.tick,
                          "to_tick": same_string_after.tick if same_string_after else note.tick,
                          "overlap_ticks": slide_overlap})
    return durations, generated


def _pitch_bend_bytes(semitones: float, range_semitones: float) -> bytes:
    if range_semitones <= 0:
        range_semitones = 2.0
    value = round(8192 + (semitones / range_semitones) * 8192)
    value = max(0, min(16383, value))
    return bytes([0xE0, value & 127, (value >> 7) & 127])


def _bend_curve_events(note: NoteEvent, duration: int, channel: int, config: dict[str, Any],
                       warnings: list[str]) -> list[tuple[int, bytes]]:
    if not note.bend_points:
        warnings.append(f"bend at tick {note.tick} has no readable Guitar Pro bend points")
        return []
    raw_points = sorted(note.bend_points, key=lambda point: point[0])
    largest_position = max((position for position, _ in raw_points), default=0)
    position_scale = 1.0 if largest_position <= 1 else 60.0 if largest_position <= 60 else 100.0
    value_scale = str(config.get("value_scale", "divisor")).lower()
    if value_scale in {"gp_percent_full_step", "percent_of_full_step", "gp_percent"}:
        # GP bend heights are percentages of a full step: 50 = one
        # semitone, 100 = two semitones. This also preserves quarter bends
        # such as 25 = 0.5 semitone.
        to_semitones = lambda value: value / 50.0
    else:
        value_divisor = float(config.get("bend_value_divisor", 2.0))
        to_semitones = lambda value: value / value_divisor
    max_semitones = float(config.get("max_bend_semitones", config.get("pitch_bend_range_semitones", 2.0)))
    upward_only = bool(config.get("upward_only", True))

    def normalize_value(value: int) -> float:
        semitones = to_semitones(value)
        if upward_only:
            semitones = max(0.0, semitones)
        return max(-max_semitones, min(max_semitones, semitones))

    points = [(max(0.0, min(1.0, position / position_scale)), normalize_value(value))
              for position, value in raw_points]
    if points[0][0] > 0:
        points.insert(0, (0.0, 0.0))
    range_semitones = float(config.get("pitch_bend_range_semitones", 2.0))
    sample_step = max(1, int(config.get("pitch_bend_step_ticks", 10)))
    sampled: dict[int, float] = {}

    if len(points) == 1:
        sampled[round(points[0][0] * duration)] = points[0][1]
    else:
        for (start_pos, start_value), (end_pos, end_value) in zip(points, points[1:]):
            start_tick = round(start_pos * duration)
            end_tick = round(end_pos * duration)
            steps = max(1, (end_tick - start_tick + sample_step - 1) // sample_step)
            for index in range(steps + 1):
                ratio = index / steps
                tick = start_tick + round((end_tick - start_tick) * ratio)
                sampled[tick] = start_value + (end_value - start_value) * ratio

    result = []
    for offset, semitones in sorted(sampled.items()):
        event_tick = max(0, note.tick + offset - (1 if offset == 0 else 0))
        bend = _pitch_bend_bytes(semitones, range_semitones)
        result.append((event_tick, bytes([bend[0] | channel, bend[1], bend[2]])))
    end_tick = note.tick + duration
    result.append((end_tick, bytes([0xE0 | channel, 0, 64])))
    return result


def _merge_cc_envelopes(envelopes: dict[tuple[int, int], list[tuple[int, int, int, int]]],
                        events: list[tuple[int, bytes]]) -> None:
    for (channel, controller), segments in envelopes.items():
        active: list[int] | None = None
        for start, end, value, reset_value in sorted(segments):
            if active is None or start > active[1]:
                if active is not None:
                    events.extend([
                        (active[0], bytes([0xB0 | channel, controller, active[2]])),
                        (active[1], bytes([0xB0 | channel, controller, active[3]])),
                    ])
                active = [start, end, value, reset_value]
            else:
                active[1] = max(active[1], end)
                active[2] = max(active[2], value)
                active[3] = reset_value
        if active is not None:
            events.extend([
                (active[0], bytes([0xB0 | channel, controller, active[2]])),
                (active[1], bytes([0xB0 | channel, controller, active[3]])),
            ])


def _processed_velocity(note: NoteEvent, config: dict[str, Any]) -> int:
    """Apply optional per-technique velocity transforms from a profile."""
    value = note.velocity
    for name in note.techniques:
        spec = config.get("techniques", {}).get(name, {})
        rule = spec.get("velocity") if isinstance(spec, dict) else None
        if not isinstance(rule, dict):
            continue
        if "value" in rule:
            value = int(rule["value"])
        if "factor" in rule:
            value = round(value * float(rule["factor"]))
        value += int(rule.get("offset", 0))
        value = max(int(rule.get("min", 1)), min(int(rule.get("max", 127)), value))
    return max(1, min(127, value))


def _convert_part(score: Score, config: dict[str, Any]) -> tuple[list[tuple[int, bytes]], dict[str, Any]]:
    warnings = list(score.warnings)
    events: list[tuple[int, bytes]] = []
    channels = config.get("string_channels", {})
    default_channel = int(config.get("default_channel", 0))
    unassigned_channel = int(config.get("unassigned_channel", 16))
    strum_channel = int(config.get("strum_channel", 16))
    # Source instruments are isolated by convert()/write_midi(). Each part
    # retains the profile's original per-string channels on its own MIDI port.
    track_stride = 0
    techniques = config.get("techniques", {})
    combinations = config.get("combinations", [])
    used_combos: set[tuple[str, ...]] = set()
    cc_envelopes: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}
    durations, generated_legato = _legato_durations(score, config, warnings)
    sustain_mode = config.get("sustain_mode", "notated")
    if sustain_mode not in {"notated", "auto"}:
        raise ValueError("sustain_mode must be 'notated' or 'auto'")
    generated_sustains = []
    groups = {}
    for note in score.notes:
        # Unknown-string notes can safely sustain only until the same pitch.
        key = (note.source_track, note.string, note.pitch if not note.string else None)
        groups.setdefault(key, []).append(note)
    for group in groups.values():
        group.sort(key=lambda n: n.tick)
        for index, note in enumerate(group):
            if {"staccato", "palm_mute"} & set(note.techniques):
                continue
            if sustain_mode != "auto" and "let_ring" not in note.techniques:
                continue
            next_note = next((n for n in group[index + 1:] if n.tick > note.tick), None)
            part_end = score.track_ends.get(note.source_track, max((n.tick + n.duration for n in score.notes), default=0))
            end = next_note.tick if next_note else part_end
            if end > note.tick + durations[id(note)]:
                generated_sustains.append({"source_track": note.source_track, "string": note.string,
                                           "tick": note.tick, "old_duration": note.duration,
                                           "duration": end - note.tick})
                durations[id(note)] = end - note.tick

    def emit_rule(rule: dict[str, Any], channel: int, tick: int, duration: int) -> None:
        if str(rule.get("type", "keyswitch")).lower() == "cc" and rule.get("reset_at_note_off"):
            controller = int(rule.get("controller", 1)) & 127
            start = max(0, tick + int(rule.get("offset_ticks", 0)))
            end = tick + duration
            cc_envelopes.setdefault((channel, controller), []).append(
                (start, end, int(rule.get("value", 127)) & 127, int(rule.get("reset_value", 0)) & 127))
            return
        events.extend(_event_from_rule(rule, channel, tick, warnings, duration))

    for n in score.notes:
        note_duration = durations[id(n)]
        track_offset = max(0, n.source_track - 1) * track_stride
        if "strum" in n.techniques:
            channel = strum_channel - 1 + track_offset
        elif n.string == 0:
            channel = unassigned_channel - 1 + track_offset
        else:
            channel = int(channels.get(str(n.string), channels.get(n.string, default_channel))) - 1 + track_offset
        if not 0 <= channel <= 15:
            warnings.append(f"invalid channel for string {n.string}: {channel + 1}; using 1")
            channel = 0
        events.append((n.tick, bytes([0x90 | channel, n.pitch & 127, _processed_velocity(n, config) & 127])))
        events.append((n.tick + note_duration, bytes([0x80 | channel, n.pitch & 127, 0])))
        if "bend" in n.techniques:
            bend_spec = techniques.get("bend", {})
            events.extend(_bend_curve_events(n, note_duration, channel,
                                             bend_spec if isinstance(bend_spec, dict) else {}, warnings))
        matched_techniques = set()
        techset = set(n.techniques)
        for combo in combinations:
            required = tuple(combo.get("when", []))
            if set(required).issubset(techset):
                matched_techniques.update(required); used_combos.add(required)
                for rule in combo.get("events", []): emit_rule(rule, channel, n.tick, note_duration)
        for name in n.techniques:
            if name in techniques:
                if name not in matched_techniques:
                    spec = techniques[name]
                    rules = spec if isinstance(spec, list) else spec.get("events", [])
                    for rule in rules:
                        emit_rule(rule, channel, n.tick, note_duration)
            elif name not in {"strum", "let_ring", "tie"} and not any(set(c.get("when", [])).issubset(techset) and name in c.get("when", []) for c in combinations):
                warnings.append(f"unmapped technique: {name} at tick {n.tick} (string {n.string})")
    _merge_cc_envelopes(cc_envelopes, events)
    used_channels = sorted({(data[0] & 0x0F) + 1 for _, data in events if data and (data[0] & 0xF0) != 0xF0})
    report = {"notes": len(score.notes), "events": len(events), "tuning": score.tuning,
              "warnings": warnings, "used_combinations": [list(x) for x in sorted(used_combos)],
              "generated_legato_overlaps": generated_legato,
              "generated_sustains": generated_sustains, "sustain_mode": sustain_mode,
              "midi_tracks": used_channels,
              "split_tracks": bool(config.get("split_tracks", True)),
              "unassigned_channel": unassigned_channel,
              "strum_channel": strum_channel,
              "source_tracks": sorted({n.source_track for n in score.notes}),
              "track_channel_stride": track_stride}
    return events, report


class MidiEvents(list):
    """Tuple-compatible events carrying original-instrument track boundaries."""

    def __init__(self):
        super().__init__()
        self.parts = {}


def convert(score: Score, config: dict[str, Any]) -> tuple[list[tuple[int, bytes]], dict[str, Any]]:
    events = MidiEvents()
    reports = []
    for source in sorted({n.source_track for n in score.notes}):
        notes = [n for n in score.notes if n.source_track == source]
        label = notes[0].source_track_name or f"Guitar {source}"
        part = Score(notes, score.track_tunings.get(source, score.tuning), score.tempo,
                     [], score.track_tunings, score.track_ends)
        emitted, report = _convert_part(part, config)
        events.extend(emitted)
        events.parts[source] = (label, emitted)
        report["source_track"] = source
        report["source_track_name"] = label
        reports.append(report)
    report = dict(reports[0]) if reports else {"notes": 0, "events": 0, "midi_tracks": [], "used_combinations": []}
    report.update(notes=len(score.notes), events=len(events), source_tracks=list(events.parts),
                  parts=reports, track_channel_stride=0,
                  routing="Each source instrument uses a separate MIDI port; route each part to its own instrument instance.")
    for key in ("warnings", "generated_legato_overlaps", "generated_sustains"):
        report[key] = [item for part in reports for item in part.get(key, [])]
    report["warnings"] = list(score.warnings) + report["warnings"]
    return events, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate Guitar Pro XML/GPX to VST-oriented MIDI")
    parser.add_argument("input", type=Path)
    parser.add_argument("-c", "--config", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--sustain-mode", choices=["notated", "auto"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    score = parse_gpx(args.input)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.sustain_mode: config["sustain_mode"] = args.sustain_mode
    from preset_manager import validate_preset
    errors = validate_preset(config)
    if errors:
        parser.error("invalid preset: " + "; ".join(errors))
    events, report = convert(score, config)
    write_midi(events, args.output, score.tempo, track_names_from_config(config), bool(config.get("split_tracks", True)))
    report_path = args.report or args.output.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for warning in report["warnings"]:
        logging.warning(warning)
    logging.info("wrote %s (%d notes, %d MIDI events)", args.output, report["notes"], report["events"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
