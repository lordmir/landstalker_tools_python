# landstalker_tools_python
Landstalker Tools written in Python

## ym_instruments — YM2612 instrument bank ↔ YAML

Converts the 80-entry FM patch bank that lives in
`landstalker_disasm/code/audio/ym_instruments.asm` between the disasm's
labelled-`db` form and a human-readable YAML representation, so patches
can be inspected and edited.

### Usage

```
python landstalker.py ym_instruments decode [-o OUT.yaml] IN.asm
python landstalker.py ym_instruments encode [-o OUT.asm]  IN.yaml
```

| Flag | Meaning |
|------|---------|
| `-o`, `--output-file` | Output path. Defaults to the input file's stem with `.yaml` (decode) or `.asm` (encode). |
| `input_file` (positional) | Input asm or YAML file. |

### YAML schema

```yaml
instruments:
  - name: YM_INSTMT_00      # asm label, preserved on round-trip
    algorithm: 5             # 0..7
    feedback: 7              # 0..7
    operators:
      op1: { dt: 2, mul: 0, tl: 27,  ks: 1, ar: 31, am: 0,
             d1r: 3,  d2r: 0, d1l: 5, rr: 10, ssg_eg: 0 }
      op2: { ... }
      op3: { ... }
      op4: { ... }
```

Each operator field maps one-to-one to a YM2612 envelope/multiplier
parameter:

| Field | Bits | Range | YM2612 datasheet name |
|-------|------|-------|------------------------|
| `dt` | 3 | 0–7 | DT (detune) |
| `mul` | 4 | 0–15 | MUL (multiplier) |
| `tl` | 7 | 0–127 | TL (total level) |
| `ks` | 2 | 0–3 | RS / KS (rate scaling) |
| `ar` | 5 | 0–31 | AR (attack rate) |
| `am` | 1 | 0–1 | AM (amplitude-mod enable) |
| `d1r` | 5 | 0–31 | D1R / DR (first decay rate) |
| `d2r` | 5 | 0–31 | D2R / SR (second decay rate) |
| `d1l` | 4 | 0–15 | D1L / SL (sustain level) |
| `rr` | 4 | 0–15 | RR (release rate) |
| `ssg_eg` | 4 | 0–15 | SSG-EG mode (bit 3 = enable) |

### Byte layout

Each patch is **29 bytes**, indexed in the instruments bank as
`0x8000 + 29 × instrument_id`. The layout is dictated by the Z80 driver
routine `YM1_LoadInstrument`
(`landstalker_disasm/code/audio/sounddrv.asm:1687-1806`):

| Offset | Size | YM2612 register | Bit-fields |
|--------|------|------------------|------------|
| 0x00 | 4 | $30 + slot | `DT[6:4]`, `MUL[3:0]` |
| 0x04 | 4 | $40 + slot | `TL[6:0]` |
| 0x08 | 4 | $50 + slot | `KS[7:6]`, `AR[4:0]` |
| 0x0C | 4 | $60 + slot | `AM[7]`, `D1R[4:0]` |
| 0x10 | 4 | $70 + slot | `D2R[4:0]` |
| 0x14 | 4 | $80 + slot | `D1L[7:4]`, `RR[3:0]` |
| 0x18 | 4 | $90 + slot | `SSG-EG[3:0]` |
| 0x1C | 1 | $B0          | `Feedback[5:3]`, `Algorithm[2:0]` |

Within each 4-byte block, operators are stored in YM2612 register-slot
order (slots 0,1,2,3), which corresponds to algorithm-numbered operators
**OP1, OP3, OP2, OP4**. The YAML names operators by their algorithm
number (`op1`–`op4`); the model handles the slot remap on decode/encode.

### Note on carrier vs. modulator TL

`YM1_LoadInstrument` (`sounddrv.asm:1760-1787`) inverts the `tl` byte
*at runtime* for operators that the current algorithm marks as carriers,
writing `0x7F − patch_TL` to register `$40+slot`. Modulator operators
get `patch_TL` written through unchanged. The YAML stores the patch
bytes as they appear on disk — i.e. carriers' `tl` values look "wrong-
way-round" (127 = loudest) compared to the YM2612 register meaning. Edit
accordingly.

### References

- `landstalker_disasm/code/audio/ym_instruments.asm` — the data this
  utility reads and writes.
- `landstalker_disasm/code/audio/sounddrv.asm:1687-1806`
  (`YM1_LoadInstrument`) — defines the 29-byte layout, the `0x8000 +
  29 × n` indexing, and the carrier-TL inversion.
- YM2612 application manual / Genesis Sound Manual — operator register
  layouts (`$30/$40/$50/$60/$70/$80/$90`) and the algorithm/feedback
  byte (`$B0`).

## audio_data — pitch effects, PSG envelopes, sample table ↔ YAML

Round-trips the three editable audio data tables that live alongside
the YM patches:

* **Pitch effects (vibratos / glissandos)** — `t_PITCH_EFFECT_0..15`
  in `landstalker_disasm/code/audio/instrument_params.asm`.
* **PSG instrument envelopes** — `t_PSG_INSTRUMENT_0..15` in the same
  file.
* **DAC sample table** — the single `t_SAMPLE_LOAD_DATA` block in
  `landstalker_disasm/code/audio/samples.asm`.

The frequency, level and slot-per-algorithm tables that share
`instrument_params.asm` are hardware calibration constants and are
*not* surfaced in the YAML. To keep `encode` round-trippable, the
encoder uses the existing asm file as a template: it preserves
everything up to (but not including) the `pt_PITCH_EFFECTS:` line and
rewrites everything from there onward. `samples.asm` contains only the
sample table, so it is overwritten in full.

### Usage

```
python landstalker.py audio_data decode \
    --params instrument_params.asm \
    --samples samples.asm \
    -o audio.yaml

python landstalker.py audio_data encode \
    --params instrument_params.asm \
    --samples samples.asm \
    audio.yaml
```

| Flag | Mode | Meaning |
|------|------|---------|
| `--params` | both | `instrument_params.asm` path. On `encode`, this file is read as a template *and* rewritten in place. |
| `--samples` | both | `samples.asm` path. On `encode`, rewritten in full. |
| `-o`, `--output-file` | decode | Output YAML path (default `audio_data.yaml`). |
| `input_file` (positional) | encode | Input YAML file. |

### YAML schema

```yaml
pitch_effects:
  - name: t_PITCH_EFFECT_2
    deltas: [-3, -3, -1, 1, 3, 3, 3, 1, -1, -3]   # signed bytes
    terminator: loop                              # "loop" ($80) or "end" ($81)

psg_instruments:
  - name: t_PSG_INSTRUMENT_2
    envelope:                                     # one entry per source byte
      - {vol: 15}                                  # vol 0–15 (loudness; inverted at write-time)
      - {vol: 14}
      # ...
      - {vol: 11, hold: true}                      # bit 7 set = sustain marker
      - {vol: 10}
      - {vol: 10}
      - {vol: 9, hold: true}                       # release-time sustain

samples:
  - {rate: 0x1, bank: 0x0, length: 0x952, start: 0x0}
  # rare-but-preserved: reserved1/reserved3 if either source byte was non-zero
```

Sample-table integers are emitted as hex literals (PyYAML accepts
``0x...`` on read, so user-edited files load without quoting). The
``start`` field is the **offset within the bank window** — i.e. the
on-disk Z80 address (always in ``$8000``-``$FFFF``) minus ``$8000`` —
so consecutive samples chain naturally
(``next.start == prev.start + prev.length``). The encoder adds
``0x8000`` back when writing.

### Pitch-effect format

Each effect is a stream of bytes parsed once per frame at
`landstalker_disasm/code/audio/sounddrv.asm:1212-1236` (YM mirror) and
`:2279-2302` (PSG mirror):

* Bytes other than `$80` and `$81` are signed-byte pitch deltas added
  to the channel frequency that frame.
* `$80` rewinds the position to 0 (loop).
* `$81` halts the position counter (end / hold).

Valid `deltas` values are therefore `-126..127`. Use `terminator:
loop` (the common case) or `terminator: end` to match the original
table's last byte.

### PSG envelope format

Each envelope step is one byte, parsed at
`sounddrv.asm:2326-2391`:

* Bits 0–3 = loudness (0 silent, 15 loudest); the driver inverts this
  to the SN76489 attenuation register's 0=loudest convention at write
  time, so editing in this YAML is "louder = bigger number".
* Bit 7 marks a **sustain point**. While bit 7 is clear, the position
  counter advances each frame; once a bit-7 byte is hit, the position
  freezes and the volume is held until the next note triggers.
* On key-release, the driver scans past the current sustain byte to
  the next byte and continues — so envelopes typically have a second
  bit-7 byte downstream that becomes the release-time sustain.

The `extra_bits` field (bits 6–4 of the source byte) is omitted when
zero, which is the case for every envelope shipped in the disasm; it
exists purely so unusual padding bytes round-trip exactly.

### Sample-table format

Each entry is 8 bytes, decoded by `LoadDacSound`
(`sounddrv.asm:288-325`):

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 1 | `rate` — divisor written to `Dac_Loop+1` |
| 0x01 | 1 | reserved (`reserved1`) |
| 0x02 | 1 | `bank` — written to `BANK_TO_LOAD` |
| 0x03 | 1 | reserved (`reserved3`) |
| 0x04 | 2 | `length`, little-endian |
| 0x06 | 2 | `start` on disk = ``0x8000 + yaml_start`` (little-endian); the YAML stores the offset-within-bank form |

### References

- `landstalker_disasm/code/audio/instrument_params.asm` — pitch-effect
  and PSG-envelope source data.
- `landstalker_disasm/code/audio/samples.asm` — sample-table source data.
- `landstalker_disasm/code/audio/sounddrv.asm:288-325` (`LoadDacSound`),
  `:1212-1236` (YM pitch effect step), `:2279-2391` (PSG pitch effect
  + envelope step).
- SN76489 datasheet — channel attenuation register layout (4-bit
  inverted level).

## music — music tracks ↔ YAML

Round-trips a single music track from
`landstalker_disasm/code/audio/music/musicNN.asm` (41 tracks total,
plus `music_null.asm`). The track header is `db p0,p1,p2,tempo`
followed by 10 ``dw`` channel pointers; the rest of the file holds one
labelled `db` block per unique target. Decoded by
`Load_Music` at `sounddrv.asm:371-471`; byte 3 + 3 is written to
YM2612 register `$26` (Timer B) so it acts as the tempo divisor.

### Usage

```
python landstalker.py music decode INPUT.asm  [-o OUT.yaml]
python landstalker.py music encode INPUT.yaml [-o OUT.asm]
```

### YAML schema

```yaml
name: MUSIC_00              # label prefix used when auto-generating slot labels
comment: "; Music Track 0x00 - Bustling Street"
preamble: [0x0, 0x0, 0x0]   # bytes 0-2 of the header (always zero in the disasm)
tempo: 0xBA                  # byte 3
channels:
  YM1:
    label: MUSIC_00_YM1
    events:
      - {cmd: slide_release, value: 0x1}
      - {cmd: vibrato, effect: 2, delay: 12}
      - {cmd: instrument, index: 0x9}
      - {cmd: volume, level: 12}
      - {cmd: pan, mode: both}
      - {note: G3, duration: 0x4}
      - {rest: 0x8}
      - {note: C4, duration: 0xC}
      # ...
      - {cmd: loop, op: section_start}
      # ...
      - {cmd: loop, op: jump_start}
      - {cmd: end}
  YM2:    { label: MUSIC_00_YM2, events: [ ... ] }
  YM3:    { label: MUSIC_00_YM3, events: [ ... ] }
  YM4:    { label: MUSIC_00_YM4, events: [ ... ] }
  YM5:    { label: MUSIC_00_YM5, events: [ ... ] }
  YM6:                                 # DAC: integer pitches
    label: MUSIC_00_YM6
    events:
      - {value: 0xD, duration: 0xB}    # plays sample 13
      - {cmd: end}
  PSG1:   { label: MUSIC_00_PSG1, events: [ ... ] }
  PSG2:   { label: MUSIC_00_PSG2, events: [ ... ] }
  PSG3:   { label: MUSIC_00_PSG3, events: [ ... ] }
  PSG_noise: PSG3                      # alias to PSG3 (same dw target)
```

### Channels and aliasing

Slots are always named `YM1`–`YM6`, `PSG1`–`PSG3`, `PSG_noise`. A
slot may carry:

* `{label, events}` — its own data; encoded as a `dw` pointer + a
  `LABEL: db ...` block.
* a string matching another slot name — alias; both slots' `dw`
  pointers reference the same target label, no duplicate data block.
* a string that is *not* a slot name — external label reference (e.g.
  the SFX 06–0C tracks share `SFX_05_NOOP` defined in
  `sfx05_data.asm`); the encoder emits the `dw` line verbatim and
  writes no local block.

`music_null.asm` aliases all 10 slots to a single `MUSIC_NULL_CMD`
end-marker; `music00.asm` aliases just `PSG_noise` to `PSG3`.

### Channel byte-stream opcodes

The Z80 driver dispatches every channel through a single parser at
`sounddrv.asm:946-1043`. A byte is a command iff `byte & 0xF8 == 0xF8`;
otherwise it is a note (with bit 7 set ⇒ "duration follows", clear ⇒
"reuse previous duration") or a rest (when `byte & 0x7F == 0x70`).
Pitches `0x00`–`0x53` index `t_YM_FREQUENCIES` / `t_PSG_FREQUENCIES`
(7 octaves of chromatic notes, surfaced as `C0`–`B6`).

| Opcode | Bytes | Event in YAML | Reference |
|---|---|---|---|
| `FF 00 00` | 3 | `{cmd: end}` | `:956-976` |
| `FF lo 00` (lo≠0) | 3 | `{cmd: chain, next_op: lo}` | `:967-970` |
| `FF lo hi` (hi≠0) | 3 | `{cmd: jump, address: hi*256+lo}` | `:957-966` |
| `FE ii` | 2 | `{cmd: instrument, index: ii}` | `:984-991` |
| `FD vv` | 2 | `{cmd: volume, level: vv & 0xF}` (`raw` if upper nibble non-zero) | `:994-1002` |
| `FC vv` | 2 | `{cmd: slide_release, value: vv}` | `:2708-2745` |
| `FB vv` | 2 | `{cmd: vibrato, effect: vv>>4, delay: vv & 0xF}` | `:2752-2779` |
| `FA vv` | 2 | `{cmd: pan, mode: ...}` (`raw` if stray low bits set) | `:2786-2802` |
| `F9 vv` | 2 | `{cmd: pitch_shift, semitones: ..., fine: ...}` | `:2837-2854` |
| `F8 bb …` | 2+ | `{cmd: loop, op: ...}` (see table below) | `:2861-3006` |
| `pitch dur` (bit 7 set) | 2 | `{note: NAME, duration: dur}` or `{value: int, duration: dur}` | `:1046-1114` |
| `pitch` (bit 7 clear) | 1 | same form, `duration` reuses previous note's value | `:1100-1102` |

The `F8 bb` family encodes `(bb >> 5) & 7` as the loop sub-opcode and
`bb & 0x1F` as a parameter:

| sub | bb range | YAML `op` | Notes |
|---|---|---|---|
| 0 | `00-1F` | `section_start` | Mark loop-start pointer |
| 1 | `20-3F` | `section_end` | Mark loop-end pointer; reset pass flags |
| 2 | `40-5F` | `first_pass_only` | Skip past on subsequent passes |
| 3 | `60-7F` | `second_pass_only` | Skip ahead to next `anchor` |
| 4 | `80-9F` | `anchor` | No-op (target of subtype 3's skip) |
| 5 | `A0-BF` | `jump_start` (bb&1) / `jump_end` | Loop terminator |
| 6 | `C0-DF` | `repeat_set` | `count = (bb & 0x1F) + 1` |
| 7 | `E0-FF` | `repeat_dec` | Branch back to repeat_set if non-zero |

### Note encoding details

* **Pitches**: tone channels (FM 1–5, PSG 1–3) emit `note: NAME` with
  `NAME` in `C0`–`B6`; non-tone channels (`YM6` / DAC and `PSG_noise`)
  emit `value: INT` because the byte is a sample / noise index, not a
  pitch. The encoder accepts either form on either channel.
* **Implicit vs explicit duration**: the disasm sometimes emits the
  bit-7-set form even when the duration is unchanged (e.g. inside a
  repeat-set loop body). The decoder records this as an
  `explicit: true` flag on the affected note/rest so byte-perfect
  round-trip is preserved; you can drop the flag freely on edited
  data and the encoder will still emit the byte-7-set form whenever
  the duration differs from the previous event.
* **Pan stray bits**: if a `FA vv` byte has bits 5–1 set (which the
  driver masks off), the YAML keeps a `raw: 0xCV` field so the source
  byte round-trips exactly. Drop the `raw` field on edited data to
  emit the canonical byte for the chosen `mode`.

### References

- `landstalker_disasm/code/audio/music/*.asm` — 41 music tracks.
- `landstalker_disasm/code/audio/sounddrv.asm:371-471` (`Load_Music`)
  and `:946-3006` (channel parser + loop sub-opcodes).
- `landstalker_disasm/code/audio/instrument_params.asm` — pitch-effect
  index used by `cmd: vibrato`'s `effect` field.

## sfx — SFX header/data ↔ YAML

Round-trips a single SFX from its `sfxXX_header.asm` +
`sfxXX_data.asm` pair. The header begins with a type byte (`db 1` or
`db 2`) followed by `dw` channel pointers:

* **Type 1** has 10 pointers using the same channel slot names as
  music (`YM1`–`PSG_noise`).
* **Type 2** has 3 pointers, mapping in order to `YM4`, `YM5`, `YM6`
  (the dedicated SFX-Type-2 trio).

Decoded by `Load_SFX` at `sounddrv.asm:474-546`. Channel byte-stream
opcodes are identical to music's (see the `music` section above).

The disasm's SFX 06–0C share the `SFX_05_NOOP` end marker defined in
`sfx05_data.asm`; the YAML records this as a string-valued slot whose
value is the external label (e.g. `YM1: SFX_05_NOOP`). Note also that
`sfx_null` (header + data) is structurally a music track with type
byte 0; it is not registered in `pt_SFX` and is *not* handled by this
utility — use the `music` command if you need to round-trip it.

### Usage

```
python landstalker.py sfx decode --header HDR.asm --data DAT.asm  [-o OUT.yaml]
python landstalker.py sfx encode --header HDR.asm --data DAT.asm  INPUT.yaml
```

### YAML schema

```yaml
name: SFX_01
comment: "; SFX 01 - Skeleton Talk"
type: 0x2
channels:
  YM4:
    label: SFX_01_NOOP
    events:
      - {cmd: end}
  YM5:
    label: SFX_01_YM5
    events:
      - {cmd: instrument, index: 0x40}
      - {cmd: volume, level: 14}
      - {cmd: vibrato, effect: 0, delay: 0}
      - {cmd: slide_release, value: 0x0}
      - {note: F2, duration: 0x1}
      - {cmd: slide_release, value: 0x80}
      - {cmd: vibrato, effect: 1, delay: 0}
      - {note: F#3, duration: 0x1}
      - {note: A4, duration: 0x1}
      - {cmd: slide_release, value: 0x1}
      - {cmd: vibrato, effect: 15, delay: 0}
      - {note: B6, duration: 0xC}
  YM6: YM4         # alias to YM4 (shared end-marker label)
```

### References

- `landstalker_disasm/code/audio/sfx.asm` — `pt_SFX` pointer table and
  the include layout that links the type-2 SFX 06–0C to `sfx05_data.asm`.
- `landstalker_disasm/code/audio/sounddrv.asm:474-546` (`Load_SFX`)
  for the dispatch and channel-data initialisation.
- `landstalker_disasm/code/audio/sfx/*.asm` — 60 active SFX header
  + data pairs.
