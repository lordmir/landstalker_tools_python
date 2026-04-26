import sys
from pathlib import Path
from scripts.audio import FlowList, HexInt, format_asm_byte

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

class FlowDict(dict):
    pass

def decode_sequence(block_data: list, label: str) -> list:
    is_psg = "PSG" in label.upper()
    is_dac = "YM6" in label.upper() or "DAC" in label.upper()
    
    i = 0
    events = []
    
    while i < len(block_data):
        b = block_data[i]
        if isinstance(b, str):
            events.append(FlowDict({"raw_word": b}))
            i += 1
            continue
            
        if b <= 0xF7:
            has_duration = bool(b & 0x80)
            pitch_val = b & 0x7F
            
            event = {}
            if pitch_val == 0x70:
                event["rest"] = True
            else:
                if is_dac:
                    event["sample"] = pitch_val + 1
                else:
                    octave = pitch_val // 12
                    note_name = NOTE_NAMES[pitch_val % 12]
                    event["note"] = f"{note_name}{octave}"
                    
            if has_duration:
                i += 1
                if i < len(block_data):
                    event["length"] = block_data[i]
                
            events.append(FlowDict(event))
            i += 1
        else:
            cmd_byte = b
            if cmd_byte == 0xFF:
                i += 1
                if i < len(block_data) and isinstance(block_data[i], str):
                    events.append(FlowDict({"cmd": "jump", "target": block_data[i]}))
                    i += 1
                else:
                    if i + 1 < len(block_data) and block_data[i] == 0 and block_data[i+1] == 0:
                        events.append(FlowDict({"cmd": "stop"}))
                        i += 2
                    else:
                        events.append(FlowDict({"cmd": "jump", "raw": FlowList(block_data[i:i+2])}))
                        i += 2
            elif cmd_byte == 0xFE:
                i += 1
                events.append(FlowDict({"cmd": "set_ym_instrument", "id": HexInt(block_data[i])}))
                i += 1
            elif cmd_byte == 0xFD:
                i += 1
                val = block_data[i]
                if is_psg:
                    events.append(FlowDict({"cmd": "set_psg_instrument", "id": val >> 4, "volume": val & 0x0F}))
                else:
                    events.append(FlowDict({"cmd": "set_volume", "volume": HexInt(val)}))
                i += 1
            elif cmd_byte == 0xFC:
                i += 1
                events.append(FlowDict({"cmd": "set_key_release", "val": HexInt(block_data[i])}))
                i += 1
            elif cmd_byte == 0xFB:
                i += 1
                events.append(FlowDict({"cmd": "load_pitch_effect", "id": HexInt(block_data[i])}))
                i += 1
            elif cmd_byte == 0xFA:
                i += 1
                val = block_data[i]
                if is_psg:
                    events.append(FlowDict({"cmd": "set_master_tempo", "val": HexInt(val)}))
                else:
                    events.append(FlowDict({"cmd": "set_stereo_pan", "val": HexInt(val)}))
                i += 1
            elif cmd_byte == 0xF9:
                i += 1
                events.append(FlowDict({"cmd": "transpose", "val": HexInt(block_data[i])}))
                i += 1
            elif cmd_byte == 0xF8:
                i += 1
                arg = block_data[i]
                op = arg & 0xE0
                n = arg & 0x1F
                if op == 0x00:
                    events.append(FlowDict({"cmd": "set_loop_point_1"}))
                elif op == 0x20:
                    events.append(FlowDict({"cmd": "set_loop_point_2"}))
                elif op == 0xA0:
                    if n == 0:
                        events.append(FlowDict({"cmd": "jump_loop_point_2"}))
                    elif n == 1:
                        events.append(FlowDict({"cmd": "jump_loop_point_1"}))
                    else:
                        events.append(FlowDict({"cmd": "loop_unknown", "val": HexInt(arg)}))
                elif op == 0x40:
                    events.append(FlowDict({"cmd": "cond_break_1"}))
                elif op == 0x60:
                    events.append(FlowDict({"cmd": "cond_break_2"}))
                elif op == 0xC0:
                    events.append(FlowDict({"cmd": "start_finite_loop", "count": n + 1}))
                elif op == 0xE0:
                    events.append(FlowDict({"cmd": "end_finite_loop"}))
                else:
                    events.append(FlowDict({"cmd": "loop_unknown", "val": HexInt(arg)}))
                i += 1
            else:
                events.append(FlowDict({"cmd": "unknown", "byte": HexInt(cmd_byte)}))
                i += 1
    return events

def encode_sequence(events: list, label: str) -> list:
    is_psg = "PSG" in label.upper()
    is_dac = "YM6" in label.upper() or "DAC" in label.upper()
    
    block_data = []
    
    for e in events:
        if "raw_word" in e:
            block_data.append(e["raw_word"])
            continue
            
        if "note" in e or "rest" in e or "sample" in e:
            has_len = "length" in e
            flag = 0x80 if has_len else 0x00
            if "rest" in e:
                b = 0x70 | flag
            elif "sample" in e:
                b = (e["sample"] - 1) | flag
            else:
                note_str = e["note"]
                note_name = note_str[:-1]
                octave = int(note_str[-1])
                pitch_val = octave * 12 + NOTE_NAMES.index(note_name)
                b = pitch_val | flag
            block_data.append(b)
            if has_len:
                block_data.append(e["length"])
                
        elif "cmd" in e:
            cmd = e["cmd"]
            if cmd == "stop":
                block_data.extend([0xFF, 0, 0])
            elif cmd == "jump":
                if "raw" in e:
                    block_data.append(0xFF)
                    block_data.extend(e["raw"])
                else:
                    block_data.append(0xFF)
                    block_data.append(e["target"])
            elif cmd == "set_ym_instrument":
                block_data.extend([0xFE, e["id"]])
            elif cmd == "set_volume":
                block_data.extend([0xFD, e["volume"]])
            elif cmd == "set_psg_instrument":
                val = (e["id"] << 4) | (e["volume"] & 0x0F)
                block_data.extend([0xFD, val])
            elif cmd == "set_key_release":
                block_data.extend([0xFC, e["val"]])
            elif cmd == "load_pitch_effect":
                block_data.extend([0xFB, e["id"]])
            elif cmd == "set_master_tempo":
                block_data.extend([0xFA, e["val"]])
            elif cmd == "set_stereo_pan":
                block_data.extend([0xFA, e["val"]])
            elif cmd == "transpose":
                block_data.extend([0xF9, e["val"]])
            elif cmd == "set_loop_point_1":
                block_data.extend([0xF8, 0x00])
            elif cmd == "set_loop_point_2":
                block_data.extend([0xF8, 0x20])
            elif cmd == "jump_loop_point_2":
                block_data.extend([0xF8, 0xA0])
            elif cmd == "jump_loop_point_1":
                block_data.extend([0xF8, 0xA1])
            elif cmd == "cond_break_1":
                block_data.extend([0xF8, 0x40])
            elif cmd == "cond_break_2":
                block_data.extend([0xF8, 0x60])
            elif cmd == "start_finite_loop":
                block_data.extend([0xF8, 0xC0 | (e["count"] - 1)])
            elif cmd == "end_finite_loop":
                block_data.extend([0xF8, 0xE0])
            elif cmd == "loop_unknown":
                block_data.extend([0xF8, e["val"]])
                
    return block_data

# Test logic
test_data = [0xFC, 1, 0xFB, 0x2C, 0xFE, 9, 0xFD, 0x0C, 0xFA, 0xC0, 0xAB, 4, 0xF0, 8, 0xB0, 0x0C, 0xFF, "MUSIC_00_YM1_LOOP"]
events = decode_sequence(test_data, "MUSIC_00_YM1")
print("Events:", events)
reencoded = encode_sequence(events, "MUSIC_00_YM1")
print("Reencoded:", reencoded)
print("Matches?", reencoded == test_data)

test_dac = [0x85, 6, 0x70, 0xFF, 0, 0]
events_dac = decode_sequence(test_dac, "MUSIC_00_YM6")
print("DAC Events:", events_dac)
reencoded_dac = encode_sequence(events_dac, "MUSIC_00_YM6")
print("Matches DAC?", reencoded_dac == test_dac)

