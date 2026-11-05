"""Resolve Guitar Pro's indexed GPIF score tables into timed notes."""
from fractions import Fraction
import xml.etree.ElementTree as ET


def read_gpif(root):
    from gpbridge import NoteEvent, Score, PPQ, STANDARD_GUITAR, local, first_text

    def child(node, name):
        return next((x for x in node if local(x.tag) == name.lower()), None)

    def text(node, name, default=""):
        value = child(node, name)
        return (value.text or "").strip() if value is not None else default

    def table(name, item):
        parent = child(root, name)
        return {x.get("id"): x for x in parent if local(x.tag) == item.lower()} if parent is not None else {}

    def props(node):
        return {x.get("name", "").lower(): x for x in node.iter() if local(x.tag) == "property"}

    def prop_number(properties, key, default=0):
        node = properties.get(key.lower())
        if node is None:
            return default
        value = next((x.text for x in node.iter() if x is not node and x.text and x.text.strip()), str(default))
        return float(value)

    tracks = table("Tracks", "Track")
    bars = table("Bars", "Bar")
    voices = table("Voices", "Voice")
    beats = table("Beats", "Beat")
    rhythms = table("Rhythms", "Rhythm")
    note_table = table("Notes", "Note")
    master_track = child(root, "MasterTrack")
    order = text(master_track, "Tracks").split() if master_track is not None else []
    order = order or list(tracks)
    master_bars = child(root, "MasterBars")
    if master_bars is None or not tracks:
        raise ValueError("GPIF is missing track/master-bar tables")

    warnings, notes, staff_layout = [], [], []
    tunings, names, track_ends = {}, {}, {}
    for index, track_id in enumerate(order, 1):
        if track_id not in tracks:
            raise ValueError(f"GPIF references missing track {track_id}")
        track = tracks[track_id]
        names[index] = text(track, "Name", f"Guitar {index}")
        staves_node = child(track, "Staves")
        staves = list(staves_node) if staves_node is not None else [track]
        for staff in staves:
            properties = props(track) | props(staff)
            pitches_node = properties.get("tuning")
            pitches = first_text(pitches_node, ["pitches"], "") if pitches_node is not None else ""
            low_to_high = [int(x) for x in pitches.split()] if pitches else [40, 45, 50, 55, 59, 64]
            tuning = {i + 1: pitch for i, pitch in enumerate(reversed(low_to_high))}
            tunings[index] = tuning
            capo = int(prop_number(properties, "CapoFret"))
            staff_layout.append((index, tuning, capo))

    dynamic = {"PPP": 32, "PP": 45, "P": 58, "MP": 72, "MF": 86, "F": 100, "FF": 112, "FFF": 120}
    values = {"Whole": 1920, "Half": 960, "Quarter": 480, "Eighth": 240,
              "16th": 120, "32nd": 60, "64th": 30, "128th": 15, "256th": 7.5}
    absolute, signature = Fraction(0), (4, 4)
    for master_bar in master_bars:
        time = text(master_bar, "Time")
        if time:
            signature = tuple(int(x) for x in time.split("/"))
        measure_duration = Fraction(PPQ * 4 * signature[0], signature[1])
        references = text(master_bar, "Bars").split()
        if len(references) != len(staff_layout):
            raise ValueError("GPIF master-bar staff references do not match its tracks")
        for bar_id, (track_index, tuning, capo) in zip(references, staff_layout):
            if bar_id == "-1":
                continue
            if bar_id not in bars:
                raise ValueError(f"GPIF references missing bar {bar_id}")
            for voice_id in text(bars[bar_id], "Voices").split():
                if voice_id == "-1":
                    continue
                if voice_id not in voices:
                    raise ValueError(f"GPIF references missing voice {voice_id}")
                cursor = Fraction(0)
                for beat_id in text(voices[voice_id], "Beats").split():
                    if beat_id not in beats:
                        raise ValueError(f"GPIF references missing beat {beat_id}")
                    beat = beats[beat_id]
                    ref = child(beat, "Rhythm")
                    rhythm = rhythms.get(ref.get("ref")) if ref is not None else None
                    if rhythm is None:
                        raise ValueError(f"GPIF beat {beat_id} has no valid rhythm")
                    value = text(rhythm, "NoteValue", "Quarter")
                    if value not in values:
                        raise ValueError(f"Unsupported GPIF rhythm {value}")
                    duration = Fraction(values[value])
                    dot = child(rhythm, "AugmentationDot")
                    dots = int(dot.get("count", "1")) if dot is not None else 0
                    duration *= sum((Fraction(1, 2 ** i) for i in range(dots + 1)), Fraction(0))
                    tuplet = child(rhythm, "PrimaryTuplet")
                    if tuplet is not None:
                        duration *= Fraction(int(tuplet.get("den", "2")), int(tuplet.get("num", "3")))
                    for note_id in text(beat, "Notes").split():
                        if note_id not in note_table:
                            raise ValueError(f"GPIF references missing note {note_id}")
                        node = note_table[note_id]
                        properties = props(node)
                        raw_string = int(prop_number(properties, "String", -1))
                        string = len(tuning) - raw_string if raw_string >= 0 else 0
                        fret = int(prop_number(properties, "Fret"))
                        if string in tuning:
                            pitch = tuning[string] + fret + capo
                        elif "midi" in properties:
                            pitch = int(prop_number(properties, "Midi"))
                        elif "tone" in properties and "octave" in properties:
                            pitch = 12 * (int(prop_number(properties, "Octave")) + 1) + int(prop_number(properties, "Tone"))
                        else:
                            warnings.append(f"GPIF note {note_id} has no playable string/pitch; skipped")
                            continue
                        techniques = []
                        tags = {local(x.tag) for x in node.iter()}
                        for tag, technique in (("palmmuted", "palm_mute"), ("muted", "palm_mute"),
                                               ("letring", "let_ring"), ("vibrato", "vibrato")):
                            if tag in tags or tag in properties:
                                techniques.append(technique)
                        if "tapped" in properties or "lefthandtapped" in properties or child(beat, "Tapped") is not None:
                            techniques.append("tapping")
                        slide = int(prop_number(properties, "Slide"))
                        if slide:
                            techniques.append("slide")
                        harmonic = properties.get("harmonictype")
                        if harmonic is not None:
                            kind = first_text(harmonic, ["htype"], "").lower()
                            if kind and kind != "noharmonic":
                                techniques.append("natural_harmonic" if kind == "natural" else "artificial_harmonic")
                        if child(beat, "Brush") is not None or child(beat, "Arpeggio") is not None:
                            techniques.append("strum")
                        accent = text(node, "Accent", "0")
                        if int(accent) & 1:
                            techniques.append("staccato")
                        bend_points = []
                        if "bended" in properties:
                            techniques.append("bend")
                            for label, offset in (("Origin", 0), ("Middle", 50), ("Destination", 100)):
                                key = f"Bend{label}Value"
                                if key.lower() in properties:
                                    bend_points.append((round(prop_number(properties, f"Bend{label}Offset", offset) * .6),
                                                        round(prop_number(properties, key))))
                        tie = child(node, "Tie")
                        note = NoteEvent(round(absolute + cursor), max(1, round(duration)), string, fret,
                                         dynamic.get(text(beat, "Dynamic", "F"), 100), techniques, pitch,
                                         bend_points, track_index, names[track_index],
                                         tie is not None and tie.get("origin", "false") == "true",
                                         tie is not None and tie.get("destination", "false") == "true")
                        note.hopo_origin = "hopoorigin" in properties
                        notes.append(note)
                    cursor += duration
                measure_duration = max(measure_duration, cursor)
            track_ends[track_index] = round(absolute + measure_duration)
        absolute += measure_duration
    # Hammer/pull is encoded on the source note; select the destination's rule.
    previous = {}
    for note in sorted(notes, key=lambda n: n.tick):
        key = (note.source_track, note.string)
        before = previous.get(key)
        if before is not None and getattr(before, "hopo_origin", False):
            note.techniques.append("hammer_on" if note.pitch > before.pitch else "pull_off")
        previous[key] = note
    from gpbridge import _merge_ties
    notes = _merge_ties(notes, warnings)
    if not notes:
        raise ValueError("GPIF contains no playable notes")
    tempos = [x for x in root.iter() if local(x.tag) == "automation" and text(x, "Type") == "Tempo"]
    tempo = round(float(text(tempos[0], "Value", "120").split()[0])) if tempos else 120
    if any(local(x.tag) == "repeat" for x in root.iter()):
        warnings.append("GPIF repeat marks are exported once in written order")
    return Score(notes, tunings.get(1, dict(STANDARD_GUITAR)), tempo, warnings, tunings, track_ends)
