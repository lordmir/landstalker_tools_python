# landstalker_tools_python
Landstalker Tools written in Python

## Audio Utilities

The `audio` utility is designed to extract audio data driven by the original Z80 Cube/Iwadare audio driver into human-readable YAML formats.

### Usage

To extract the audio data, run the `audio` command via the main `landstalker.py` script:

```bash
python landstalker.py audio [--disasm PATH] [--out PATH] [--out-samples PATH]
```

**Parameters:**
- `--disasm PATH`: The path to the `landstalker_disasm` directory containing the original Z80 assembly source files. Defaults to `landstalker_disasm`.
- `--out PATH`: The path where the output YAML file should be saved. Defaults to `instruments.yaml`.
- `--out-samples PATH`: The path where the extracted PCM sample metadata YAML file should be saved. Defaults to `samples.yaml`.

### Output Structure

The output `instruments.yaml` contains three main sections, heavily informed by the Z80 hardware configuration:

1. **`ym_instruments`**: Extracted from `code/audio/ym_instruments.asm`. These 29-byte blocks correspond to the hardware registers of the YM2612 FM Synthesizer. They dictate parameters like Algorithm, Feedback, Detune, Multiple, Total Level, Key Scale, Amplitude Modulation, and SSG-EG settings across its 4 operators.
2. **`psg_instruments`**: Extracted from `code/audio/instrument_params.asm`. Because the SN76489 (PSG) lacks internal hardware envelopes, these variable-length arrays define software-driven volume attenuation sequences (from `0` to `15`), split cleanly into `attack` and `release` phases.
3. **`pitch_effects`**: Extracted from `code/audio/instrument_params.asm`. These define variable-length pitch modification sequences used for software-driven vibrato and pitch bends.

The output `samples.yaml` contains an array of `samples`:

- **`samples`**: Extracted from `code/audio/samples.asm`. Each 8-byte entry in `t_SAMPLE_LOAD_DATA` defines the playback characteristics for a DAC sample, including its custom delay timer (modifying the sample rate), ROM bank, size, and starting address within the `0x8000`-`0xFFFF` mapped window.
