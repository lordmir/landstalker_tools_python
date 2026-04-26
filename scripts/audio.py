import argparse
import re
import sys
from pathlib import Path
import yaml

def parse_asm_data(asm_text: str) -> dict[str, list[int]]:
    """
    Parses an assembly file containing data blocks (db directives).
    
    Args:
        asm_text: The text content of the assembly file.
        
    Returns:
        A dictionary mapping labels to lists of integer byte values.
    """
    data: dict[str, list[int]] = {}
    current_label: str | None = None
    
    for line in asm_text.splitlines():
        # Remove comments
        line = line.split(';')[0].strip()
        if not line:
            continue
            
        # Check for label
        label_match = re.match(r'^([a-zA-Z0-9_]+):', line)
        if label_match:
            current_label = label_match.group(1)
            data[current_label] = []
            line = line[label_match.end():].strip()
            
        if not line and current_label:
            continue
            
        # Parse db
        if line.lower().startswith('db '):
            if current_label is None:
                continue
            values = line[3:].split(',')
            for v in values:
                v = v.strip()
                if not v:
                    continue
                if v.endswith('h') or v.endswith('H'):
                    data[current_label].append(int(v[:-1], 16))
                elif v.startswith('0x') or v.startswith('0X'):
                    data[current_label].append(int(v, 16))
                else:
                    try:
                        data[current_label].append(int(v))
                    except ValueError:
                        pass
    return data

class FlowList(list):
    """List subclass to force YAML to output as flow-style (inline)."""
    pass

def flow_list_rep(dumper, data):
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

yaml.add_representer(FlowList, flow_list_rep)

class HexInt(int):
    """Int subclass to force YAML to output as hex string."""
    pass

def hex_int_rep(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:int', f"0x{data:02X}")

yaml.add_representer(HexInt, hex_int_rep)

def format_ym_instrument(data: list[int]) -> dict | FlowList:
    """
    Formats a 29-byte YM instrument into a human-readable dictionary.
    
    Args:
        data: List of integer values for the YM instrument.
        
    Returns:
        A dictionary with named parameters, or a FlowList of HexInts if length is not 29.
    """
    if len(data) != 29:
        return FlowList([HexInt(v) for v in data])
        
    # YM2612 hardware operators are ordered: +0 (Op1), +4 (Op3), +8 (Op2), +C (Op4)
    # The driver writes them linearly as +0, +4, +8, +C.
    op_names = ["op1", "op3", "op2", "op4"]
    
    return {
        "feedback_algo": HexInt(data[28]),
        "operators": {
            op_names[i]: {
                "det_mult": HexInt(data[0+i]),
                "total_level": HexInt(data[4+i]),
                "ks_ar": HexInt(data[8+i]),
                "am_dr": HexInt(data[12+i]),
                "sr": HexInt(data[16+i]),
                "sl_rr": HexInt(data[20+i]),
                "ssg_eg": HexInt(data[24+i])
            }
            for i in range(4)
        }
    }

def format_psg_instrument(data: list[int]) -> dict:
    """
    Formats a PSG instrument list into attack and release phases.
    
    Args:
        data: List of integer values for the PSG instrument.
        
    Returns:
        Dictionary with 'attack' and 'release' FlowLists.
    """
    attack = []
    release = []
    in_release = False
    
    for v in data:
        is_sustain = bool(v & 0x80)
        val = v & 0x7F
        
        if not in_release:
            attack.append(val)
            if is_sustain:
                in_release = True
        else:
            release.append(val)
            if is_sustain:
                break
                
    result = {"attack": FlowList(attack)}
    if release:
        result["release"] = FlowList(release)
    return result

def format_pitch_effect(data: list[int]) -> FlowList:
    """
    Formats a pitch effect list as signed integers, omitting the 0x80 end marker.
    
    Args:
        data: List of integer values for the pitch effect.
        
    Returns:
        FlowList of signed integers.
    """
    result = []
    for v in data:
        if v == 0x80:
            break
        else:
            result.append(v if v < 128 else v - 256)
    return FlowList(result)

def extract_instruments(disasm_dir: Path, output_file: Path) -> None:
    """
    Extracts YM and PSG instrument data from assembly files and writes to YAML.
    
    Args:
        disasm_dir: Path to the landstalker_disasm directory.
        output_file: Path to the output YAML file.
    """
    ym_file = disasm_dir / "code" / "audio" / "ym_instruments.asm"
    psg_file = disasm_dir / "code" / "audio" / "instrument_params.asm"
    
    ym_text = ym_file.read_text(encoding="utf-8")
    psg_text = psg_file.read_text(encoding="utf-8")
    
    ym_parsed = parse_asm_data(ym_text)
    psg_parsed = parse_asm_data(psg_text)
    
    output_data: dict[str, dict] = {
        "ym_instruments": {
            k: format_ym_instrument(v) for k, v in ym_parsed.items() if k.startswith("YM_INSTMT_")
        },
        "psg_instruments": {
            k: format_psg_instrument(v) for k, v in psg_parsed.items() if k.startswith("t_PSG_INSTRUMENT_")
        },
        "pitch_effects": {
            k: format_pitch_effect(v) for k, v in psg_parsed.items() if k.startswith("t_PITCH_EFFECT_")
        }
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=None, sort_keys=False)
        
    print(f"Successfully exported instrument data to {output_file}")

def extract_samples(disasm_dir: Path, output_file: Path) -> None:
    """
    Extracts PCM sample metadata from the assembly and writes to YAML.
    
    Args:
        disasm_dir: Path to the landstalker_disasm directory.
        output_file: Path to the output YAML file.
    """
    samples_file = disasm_dir / "code" / "audio" / "samples.asm"
    samples_text = samples_file.read_text(encoding="utf-8")
    
    parsed = parse_asm_data(samples_text)
    if "t_SAMPLE_LOAD_DATA" not in parsed:
        print("Warning: t_SAMPLE_LOAD_DATA not found in samples.asm")
        return
        
    data = parsed["t_SAMPLE_LOAD_DATA"]
    samples_list = []
    
    # Each entry is 8 bytes
    for i in range(0, len(data), 8):
        chunk = data[i:i+8]
        if len(chunk) < 8:
            break
            
        delay = chunk[0]
        bank = chunk[2]
        length = chunk[4] | (chunk[5] << 8)
        start_addr = (chunk[6] | (chunk[7] << 8)) - 0x8000
        
        # ID is just 1-indexed count based on driver usage
        sample_id = (i // 8) + 1
        
        samples_list.append({
            "id": sample_id,
            "delay": delay,
            "bank": HexInt(bank),
            "length": length,
            "start_addr": HexInt(start_addr)
        })
        
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump({"samples": samples_list}, f, default_flow_style=False, sort_keys=False)
        
    print(f"Successfully exported sample data to {output_file}")

def main(args: list[str]) -> None:
    """
    Entry point for the audio script.
    
    Args:
        args: Command line arguments.
    """
    parser = argparse.ArgumentParser(description="Extracts audio data to YAML.")
    parser.add_argument("--disasm", type=Path, default=Path("landstalker_disasm"), help="Path to landstalker_disasm directory")
    parser.add_argument("--out", type=Path, default=Path("instruments.yaml"), help="Path to output YAML file")
    parser.add_argument("--out-samples", type=Path, default=Path("samples.yaml"), help="Path to output samples YAML file")
    
    parsed_args = parser.parse_args(args)
    extract_instruments(parsed_args.disasm, parsed_args.out)
    extract_samples(parsed_args.disasm, parsed_args.out_samples)

if __name__ == "__main__":
    main(sys.argv[1:])
