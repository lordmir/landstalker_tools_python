# Landstalker Z80 Audio Driver: Music & SFX Format Specification

This document details the bytecode format used by the Z80 Cube/Iwadare audio driver in Sega Genesis's *Landstalker* for music and sound effect sequencing.

## 1. Track Headers

Each audio track file (e.g., `music00.asm`, `sfx01_header.asm`) begins with a fixed header, defining the track's type and pointing to the sequence data.

### Music Tracks
*   **Byte 0:** `0x00` (Indicates a music track).
*   **Bytes 1-2:** `MUSIC_DOESNT_USE_SAMPLES` flag/timer (16-bit).
*   **Byte 3:** **Tempo.** This value is loaded directly into the YM2612 "Timer B" register, dictating the master clock speed for the track.
*   **Pointers (20 Bytes):** Exactly 10 16-bit absolute pointers, ordered strictly as: 
    `YM1`, `YM2`, `YM3`, `YM4`, `YM5`, `YM6` (DAC), `PSG1`, `PSG2`, `PSG3`, `PSG4` (Noise).

### Sound Effects (SFX)
Sound Effects use the exact same sequence commands as music, but their headers define how they interrupt the audio engine.
*   **Type 1 SFX (Byte 0 = `0x01`):** These major jingles/fanfares completely overtake the audio engine. They are immediately followed by **10 pointers** (just like a music track).
*   **Type 2 SFX (Byte 0 > `0x01`):** These short sound effects play *over* the background music. They are followed by exactly **3 pointers**. The driver temporarily hijacks specific channels (usually YM5, YM6/DAC, and PSG3) to play these 3 sequences, leaving the other background music channels undisturbed.

## 2. Channel Command Sequences

Each channel pointer points to a sequence of bytes. The driver parses these frame-by-frame as either **Notes/Rests** or **Control Commands**.

### Notes and Rests (`0x00` - `0xEF`)

*   **Pitch (`0x00` - `0x6F`):** Values in this range represent note pitches. They act as indexes into a hardware-specific frequency lookup table (`t_YM_FREQUENCIES` or `t_PSG_FREQUENCIES`).
    *   **Unified Pitch Mapping:** The assembler values map directly to a chromatic scale starting at **C0** (`0x00`). Every 12 values represents a full octave. The byte value can be calculated as `(Octave * 12) + Semitone_Offset` (where C=0, C#=1, D=2, etc.). For example: `0x00` is C0, `0x0C` is C1, and `0x18` is C2. To compensate for the fact that the PSG hardware frequency table begins at A1, the audio driver dynamically subtracts `0x15` (21 semitones) from the note value before looking up the frequency for a PSG channel. This allows composers to use the exact same note values for both YM and PSG channels.
    *   **DAC Exception (YM6 Channel):** For the 6th YM channel, the driver reinterprets pitch values as **PCM Sample IDs**. A byte value of `0x00` plays Sample 1 (the 1st entry in `t_SAMPLE_LOAD_DATA`). `0x05` plays Sample 6.
*   **Rest (`0x70`):** Mutes the channel (triggers a Key Off). This also works for the DAC channel to silence a playing sample.
*   **Duration Flag (`0x80`):** The highest bit acts as a duration toggle to compress the sequence data. This applies to all channels, including the DAC.
    *   If a note byte has the MSB **cleared** (e.g., `0x0C`), the note plays using the **same duration as the previous note**.
    *   If a note byte has the MSB **set** (e.g., `0x8C`), the byte immediately following it will be read as the new duration timer (in frames). Example: `0x8C, 0x06` plays note `0x0C` (or Sample 13 on DAC) for `6` frames.

### Control Commands (`0xF8` - `0xFF`)

Commands from `0xF8` to `0xFF` change the state of the channel. While most function identically across both the YM2612 and SN76489 (PSG), there are notable hardware-specific differences.

| Command | YM2612 Behavior | SN76489 (PSG) Behavior | Description |
| :--- | :--- | :--- | :--- |
| **`0xFF`** | Jump | Jump | Reads the next 2 bytes as a 16-bit pointer and jumps to it. `0x0000` stops the channel. |
| **`0xFE`** | Set YM Instrument | *Ignored* | Reads the next byte and sets it as the active YM hardware instrument index. |
| **`0xFD`** | Set Volume | Set Instrument & Volume | **YM:** Reads 1 byte for volume (`0x00`-`0x0F`) and applies the active YM instrument.<br>**PSG:** Reads 1 byte. Upper nibble is the PSG Instrument ID (0-15); lower nibble is the Volume (0-15). |
| **`0xFC`** | Set Key Release | Set Key Release | Reads the next byte to configure the envelope "release point" within the note's duration. |
| **`0xFB`** | Load Pitch Effect | Load Pitch Effect | Reads the next byte as an index to load a vibrato/pitch-bend effect (`t_PITCH_EFFECT_XX`). |
| **`0xFA`** | Set Stereo Pan | **Set Master Tempo** | **YM:** Reads 1 byte for Left/Right/Center panning.<br>**PSG:** Reads 1 byte and writes it to YM2612 Timer B, allowing mid-song tempo changes! |
| **`0xF9`** | Transpose | Transpose | Reads the next byte as a global pitch-shift offset applied to all subsequent notes. |
| **`0xF8`** | Loop Control | Loop Control | Reads the next byte to define complex loop structures. See below. |

## 3. Loop Controls (`0xF8`)

The `0xF8` command handles all looping and branching. It reads exactly one additional parameter byte. The upper 3 bits of this parameter define the operation, and the lower 5 bits serve as arguments (such as loop counters).

### Infinite Loops & Conditional Breaks

Used to create infinite repeating sections or loops with programmed "breakout" paths.

*   **`0xF8, 0x00`:** Set Loop Point 1 (Saves current sequence position).
*   **`0xF8, 0x20`:** Set Loop Point 2 (Saves a secondary position and clears break flags).
*   **`0xF8, 0xA0`:** Unconditional Jump to Loop Point 2.
*   **`0xF8, 0xA1`:** Unconditional Jump to Loop Point 1.
*   **`0xF8, 0x40`:** Conditional Break 1. On first execution, sets a flag. On second execution, fast-forwards the sequence data until it finds an `0xF8, 0x60` command and resumes from there.
*   **`0xF8, 0x60`:** Conditional Break 2. Similar to `0x40`, but uses a second flag and fast-forwards until it finds an `0xF8, 0x80` command.

*(Note: `0xF8, 0x60` and `0xF8, 0x80` also serve as destination markers for the conditional break commands).*

### Finite Loops

Used for standard bounded repetitions.

*   **`0xF8, 0xCn` (Start Finite Loop):** `n` represents the lower 5 bits. The driver saves the current position as Loop Point 3, sets the loop counter to `n + 1`. (e.g., `0xF8, 0xC3` loops 4 times).
*   **`0xF8, 0xE0` (End Finite Loop):** Decrements the loop counter. If > 0, it jumps back to Loop Point 3. If 0, it exits the loop and continues to the next byte.