# Shreddage 3.5 Archtop Profile Verification

- Source: `Documentation/Manual.pdf`, Shreddage 3.5 Archtop Manual.
- Profile status: documented from the manual; not verified in a running Kontakt instance.
- Octave convention: the manual identifies C-2 as the lowest MIDI note, so C-2 = MIDI 0 and C0 = MIDI 24.
- Mapped: Palm Mute C#0, Staccato D0, Tremolo F#0, Tapping A#0, Natural Harmonics G#0, Artificial Harmonics A0, Slide C1.
- Vibrato: sends Mod Wheel CC1 while the marked note sounds and returns it to 0 at note-off. The Kontakt patch must select CC1 as its vibrato controller.
- Bends: Guitar Pro bend points are translated to an upward-only sampled MIDI pitch-wheel curve. The profile interprets GP heights as percentages of a full step (25 = 0.5 semitone, 50 = 1 semitone, 100 = 2 semitones), clamps at +2 semitones, and resets to center at note-off.
- Hammer-on/pull-off: same-string adjacent notes get a 5-tick overlap by default. The GP Bridge interface exposes this as an adjustable 0-100 tick setting; the profile also stores the default for command-line/MCP use.
- Per-string channels: string 1/high E to channel 1 through string 6/low E to channel 6, matching MIDI Guitar Mode. Kontakt input must be OMNI when MIDI Guitar Mode is enabled.
- Validation: JSON parsing, preset schema checks, and converter event smoke checks passed.
- Kontakt/MIDI monitor test: not performed in this environment.
- Limitations: TACT mappings are editable in Kontakt. A generic Guitar Pro harmonic marker defaults to Artificial Harmonics; use the specific Natural Harmonic marker when natural harmonics are intended. The Kontakt patch must be set to CC1 vibrato control and its pitch-bend range must match the profile.
