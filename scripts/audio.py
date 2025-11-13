import pyaudio
import wave
import io
import yaml

ROM_FILE = "landstalker.bin"

BANK1_BEGIN = 0x1E0000
BANK1_END = 0x1E8000
BANK2_BEGIN = BANK1_END
BANK2_END = 0x1F0000
BANK3_BEGIN = BANK2_END
BANK3_END = 0x1F6000
DRV_BEGIN = BANK3_END
DRV_END = 0x1F8000
BANK4_BEGIN = DRV_END
BANK4_END = 0x200000

BANK_OFFSET = 0x8000
SFX_TABLE_OFFSET = 0x1594
NUM_SFX = 0x3A
BANK3_TABLE_OFFSET = 0x0000
NUM_BANK3_TRACKS = 32
BANK4_TABLE_OFFSET = 0x0910
NUM_BANK4_TRACKS = 32

TYPE_1_CHANNELS = ["YM1", "YM2", "YM3", "YM4", "YM5", "DAC", "PSG1", "PSG2", "PSG3", "PSGN"]
TYPE_1A_CHANNELS = ["YM1", "YM2", "YM3", "YM4", "YM5", "YM6", "PSG1", "PSG2", "PSG3", "PSGN"]
TYPE_2_CHANNELS = ["YM4", "YM5", "DAC"]

NOTES = ["C 1", "C#1", "D 1", "D#1", "E 1", "F 1", "F#1", "G 1", "G#1", "A 1", "A#1", "B 1",
         "C 2", "C#2", "D 2", "D#2", "E 2", "F 2", "F#2", "G 2", "G#2", "A 2", "A#2", "B 2",
         "C 3", "C#3", "D 3", "D#3", "E 3", "F 3", "F#3", "G 3", "G#3", "A 3", "A#3", "B 3",
         "C 4", "C#4", "D 4", "D#4", "E 4", "F 4", "F#4", "G 4", "G#4", "A 4", "A#4", "B 4",
         "C 5", "C#5", "D 5", "D#5", "E 5", "F 5", "F#5", "G 5", "G#5", "A 5", "A#5", "B 5",
         "C 6", "C#6", "D 6", "D#6", "E 6", "F 6", "F#6", "G 6", "G#6", "A 6", "A#6", "B 6",
         "C 7", "C#7", "D 7", "D#7", "E 7", "F 7", "F#7", "G 7", "G#7", "A 7", "A#7", "B 7",
         "C 8"]

def process_loop_cmd(loop_cmd):
    if loop_cmd == 0x00:
        return {"command": "START_LOOP_A", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "Start loop A"}
    elif loop_cmd == 0xA1:
        return {"command": "END_LOOP_A", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "End loop A"}
    elif loop_cmd == 0x20:
        return {"command": "START_LOOP_B", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "Start Loop B"}
    elif loop_cmd == 0xA0:
        return {"command": "END_LOOP_B", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "End Loop B"}
    elif loop_cmd == 0x40:
        return {"command": "LOOP_B_SECTION_1_BEGIN", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "Loop B: Section 1 begin (play once, then jump to section 2)"}
    elif loop_cmd == 0x60:
        return {"command": "LOOP_B_SECTION_2_BEGIN", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "Loop B: Section 2 begin (play once, then jump to section 3)"}
    elif loop_cmd == 0x80:
        return {"command": "LOOP_B_SECTION_3_BEGIN", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "Loop B: Section 3 begin (no skip)"}
    elif loop_cmd >= 0xC0 and loop_cmd <= 0xDF:
        loop_count = loop_cmd & 0x1F
        return {"command": "START_LOOP_C", "bytes": bytes([0xF8, loop_cmd]), "operands": {"count": loop_count}, "description": f"Start Loop C, repeat {loop_count} times"}
    elif loop_cmd >= 0xE0:
        return {"command": "END_LOOP_C", "bytes": bytes([0xF8, loop_cmd]), "operands": {}, "description": "End Loop C"}
    else:
        return {"command": "UNKNOWN_LOOP_CMD", "bytes": bytes([0xF8, loop_cmd]), "operands": {"command": loop_cmd}, "description": f"Unknown loop command {loop_cmd:02X}"}

def process_ym_channel(offset, bank):
    commands = []
    while True:
        commandbyte = bank[offset]
        offset += 1
        if commandbyte == 0xFF:
            address = int.from_bytes(bank[offset:offset + 2], "little")
            offset += 2
            if address == 0x0000:
                commands.append({"bytes": bank[offset-3:offset], "command": "END", "operands": {}, "description": "End of commands"})
                break
            elif address < 0x100:
                commands.append({"bytes": bank[offset-3:offset], "command": "SET_OP", "operands": {"operation": address}, "description": f"Set operation to {address:02X}"})
            else:
                commands.append({"bytes": bank[offset-3:offset], "command": "JUMP", "operands": {"address": address}, "description": f"Jump to address {address:04X}"})
                offset = address
        elif commandbyte == 0xFE:
            instrument = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_INSTRUMENT", "operands": {"instrument": instrument}, "description": f"Set instrument to {instrument:02X}"})
        elif commandbyte == 0xFD:
            volume = bank[offset] & 0x0F
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_VOLUME", "operands": {"volume": volume}, "description": f"Set volume to {volume:02X} and reload instrument"})
        elif commandbyte == 0xFC:
            op = bank[offset]
            offset += 1
            if op < 0x80:
                duration = op + 1
                commands.append({"bytes": bank[offset-2:offset], "command": "SET_KEY_RELEASE", "operands": {"duration": duration}, "description": f"Set key release to {duration} ticks before note end"})
            elif op == 0x80:
                commands.append({"bytes": bank[offset-2:offset], "command": "SUSTAIN", "operands": {}, "description": f"Sustain until next note"})
            elif op < 0xFF:
                speed = op & 0x7F
                commands.append({"bytes": bank[offset-2:offset], "command": "SET_PITCH_SLIDE", "operands": {"speed": speed}, "description": f"Set pitch slide speed to {speed}"})
            else: # 0xFFs
                commands.append({"bytes": bank[offset-2:offset], "command": "STOP_PITCH_SLIDE", "operands": {}, "description": f"Stop pitch slide"})
        elif commandbyte == 0xFB:
            vibrato = bank[offset] >> 4
            trigger = 1 << (bank[offset] & 0x0F)
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_VIBRATO", "operands": {"vibrato": vibrato, "trigger": trigger}, "description": f"Set vibrato depth {vibrato}, trigger {trigger}"})
        elif commandbyte == 0xFA:
            left_channel = (bank[offset] & 0x80) > 0
            right_channel = (bank[offset] & 0x40) > 0
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_STEREO", "operands": {"left": left_channel, "right": right_channel}, "description": f"Set stereo: Left {left_channel}, Right {right_channel}"})
        elif commandbyte == 0xF9:
            shift_direction = (bank[offset] & 0x80) >> 7
            shift_amount = (bank[offset] & 0x70) >> 4
            note_shift = bank[offset] & 0x0F
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_NOTE_SHIFT", "operands": {"shift_direction": shift_direction, "shift_amount": shift_amount, "note_shift": note_shift}, "description": f"Set note shift: Direction {'UP' if shift_direction == 0 else 'DOWN'}, Frequency Amount {shift_amount}, Note Shift {note_shift}"})
        elif commandbyte == 0xF8:
            loop_cmd = bank[offset]
            offset += 1
            commands.append(process_loop_cmd(loop_cmd))
        elif commandbyte == 0xF0:
            duration = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_NOTE_LENGTH", "operands": {"duration": duration}, "description": f"Set note length to {duration} and wait for {duration} ticks"})
        elif (commandbyte & 0x7F) == 0x70:
            if commandbyte > 0x7F:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_SET_DUR", "operands": {"note": "PAUSE", "duration": duration}, "description": f"Pause and set new note duration to {duration:02X} ticks"})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PAUSE", "operands": {"note": "PAUSE"}, "description": "Pause for note length"})
        elif (commandbyte & 0x7F) < len(NOTES):
            note_idx = commandbyte & 0x7F
            note = NOTES[note_idx]
            length_set = (commandbyte > 0x7F)
            if length_set:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PLAY_NOTE_SET_DUR", "operands": {"note": note, "duration": duration}, "description": f"Play note {note} ({note_idx:02X}) and set new note duration to {duration:02X}."})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PLAY_NOTE", "operands": {"note": note}, "description": f"Play note {note} ({note_idx:02X}) with current duration."})
        else:
            commands.append({"bytes": bytes([commandbyte]), "command": "UNKNOWN_CMD", "operands": {"command": commandbyte}, "description": f"Unknown command byte {commandbyte:02X}"})
    return commands

def process_dac_channel(offset, bank):
    commands = []
    while True:
        commandbyte = bank[offset]
        offset += 1
        if commandbyte == 0xFF:
            address = int.from_bytes(bank[offset:offset + 2], "little")
            offset += 2
            if address == 0x0000:
                commands.append({"bytes": bank[offset-3:offset], "command": "END", "operands": {}, "description": "End of commands"})
                break
            else:
                commands.append({"bytes": bank[offset-3:offset], "command": "JUMP", "operands": {"address": address}, "description": f"Jump to address {address:04X}"})
                offset = address
        elif commandbyte == 0xFC:
            op = bank[offset]
            offset += 1
            if op < 0x80:
                duration = op
                commands.append({"bytes": bank[offset-2:offset], "command": "SET_PLAY_LENGTH", "operands": {"duration": duration}, "description": f"Stop playing sample {duration} ticks before sample end"})
            else:
                commands.append({"bytes": bank[offset-2:offset], "command": "PLAY_FULL_SAMPLE", "operands": {}, "description": f"Ignore play length, play full sample"})
        elif commandbyte == 0xFA:
            left_channel = (bank[offset] & 0x80) > 0
            right_channel = (bank[offset] & 0x40) > 0
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_STEREO", "operands": {"left": left_channel, "right": right_channel}, "description": f"Set stereo: Left {left_channel}, Right {right_channel}"})
        elif commandbyte == 0xF8:
            loop_cmd = bank[offset]
            offset += 1
            commands.append(process_loop_cmd(loop_cmd))
        elif commandbyte == 0xF0:
            duration = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_FOR_DURATION", "operands": {"duration": duration}, "description": f"Set sample play length to {duration} and wait for {duration} ticks"})
        elif (commandbyte & 0x7F) == 0x70:
            if commandbyte > 0x7F:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_SET_DUR", "note": "PAUSE", "operands": {"note": "PAUSE", "duration": duration}, "description": f"Pause and set new sample duration to {duration:02X} ticks"})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PAUSE", "operands": {"note": "PAUSE"}, "description": "Pause for sample length"})
        else:
            sample_idx = commandbyte & 0x7F
            length_set = (commandbyte > 0x7F)
            if length_set:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PLAY_SAMPLE_SET_DUR", "operands": {"note": f"SAMPLE_{sample_idx}", "duration": duration}, "description": f"Play sample {sample_idx} and set new sample duration to {duration:02X}."})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PLAY_SAMPLE", "operands": {"note": f"SAMPLE_{sample_idx}"}, "description": f"Play sample {sample_idx} with current duration."})
    return commands

def process_psg_channel(offset, bank):
    commands = []
    while True:
        commandbyte = bank[offset]
        offset += 1
        if commandbyte == 0xFF:
            address = int.from_bytes(bank[offset:offset + 2], "little")
            offset += 2
            if address == 0x0000:
                commands.append({"bytes": bank[offset-3:offset], "command": "END", "operands": {}, "description": "End of commands"})
                break
            else:
                commands.append({"bytes": bank[offset-3:offset], "command": "JUMP", "operands": {"address": address}, "description": f"Jump to address {address:04X}"})
                offset = address
        elif commandbyte == 0xFD:
            instrument = bank[offset] >> 4
            level = bank[offset] & 0x0F
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_INSTRUMENT", "operands": {"instrument": instrument, "level": level}, "description": f"Set instrument {instrument:01X} at level {level:01X}"})
        elif commandbyte == 0xFC:
            op = bank[offset]
            offset += 1
            if op < 0x80:
                duration = op + 1
                commands.append({"bytes": bank[offset-2:offset], "command": "SET_KEY_RELEASE", "operands": {"duration": duration}, "description": f"Release key {duration} ticks before note end"})
            else:
                commands.append({"bytes": bank[offset-2:offset], "command": "NEVER_RELEASE_KEY", "operands": {}, "description": f"Never release key"})
        elif commandbyte == 0xFB:
            vibrato = bank[offset] >> 4
            trigger = 1 << (bank[offset] & 0x0F)
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_VIBRATO", "operands": {"vibrato": vibrato, "trigger": trigger}, "description": f"Set vibrato depth {vibrato}, trigger {trigger}"})
        elif commandbyte == 0xFA:
            timer = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_YM_TIMER", "operands": {"timer": timer}, "description": f"Set YM timer to {timer}"})
        elif commandbyte == 0xF9:
            shift_direction = (bank[offset] & 0x80) >> 7
            shift_amount = (bank[offset] & 0x70) >> 4
            note_shift = bank[offset] & 0x0F
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_NOTE_SHIFT", "operands": {"shift_direction": shift_direction, "shift_amount": shift_amount, "note_shift": note_shift}, "description": f"Set note shift: Direction {'UP' if shift_direction == 0 else 'DOWN'}, Frequency Amount {shift_amount}, Note Shift {note_shift}"})
        elif commandbyte == 0xF8:
            loop_cmd = bank[offset]
            offset += 1
            commands.append(process_loop_cmd(loop_cmd))
        elif commandbyte == 0xF0:
            duration = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_FOR_DURATION", "operands": {"duration": duration}, "description": f"Set note length to {duration} and wait for {duration} ticks"})
        elif (commandbyte & 0x7F) == 0x70:
            if commandbyte > 0x7F:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_SET_DUR", "operands": {"note": "PAUSE", "duration": duration}, "description": f"Pause and set new note duration to {duration:02X} ticks"})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PAUSE", "operands": {"note": "PAUSE"}, "description": "Pause for note length"})
        elif (commandbyte & 0x7F) in range(0x15, len(NOTES) + 0x15):
            note_idx = (commandbyte & 0x7F)
            note = NOTES[note_idx]
            length_set = (commandbyte > 0x7F)
            if length_set:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PLAY_NOTE_SET_DUR", "operands": {"note": note, "duration": duration}, "description": f"Play note {note} ({note_idx:02X}) and set new note duration to {duration:02X}"})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PLAY_NOTE", "operands": {"note": note}, "description": f"Play note {note} ({note_idx:02X}) with current duration."})
        else:
            commands.append({"bytes": bytes([commandbyte]), "command": "UNKNOWN_CMD", "operands": {"command": commandbyte}, "description": f"Unknown command byte {commandbyte:02X}"})
    return commands

def process_psgn_channel(offset, bank):
    commands = []
    while True:
        commandbyte = bank[offset]
        offset += 1
        if commandbyte == 0xFF:
            address = int.from_bytes(bank[offset:offset + 2], "little")
            offset += 2
            if address == 0x0000:
                commands.append({"bytes": bank[offset-3:offset], "command": "END", "operands": {}, "description": "End of commands"})
                break
            else:
                commands.append({"bytes": bank[offset-3:offset], "command": "JUMP", "operands": {"address": address}, "description": f"Jump to address {address:04X}"})
                offset = address
        elif commandbyte == 0xFD:
            instrument = bank[offset] >> 4
            level = bank[offset] & 0x0F
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "SET_INSTRUMENT", "operands": {"instrument": instrument, "level": level}, "description": f"Set instrument {instrument:01X} at level {level:01X}"})
        elif commandbyte == 0xFC:
            op = bank[offset]
            offset += 1
            if op < 0x80:
                duration = op + 1
                commands.append({"bytes": bank[offset-2:offset], "command": "SET_KEY_RELEASE", "operands": {"duration": duration}, "description": f"Release key {duration} ticks before note end"})
            else:
                commands.append({"bytes": bank[offset-2:offset], "command": "NEVER_RELEASE_KEY", "operands": {}, "description": f"Never release key"})
        elif commandbyte == 0xF8:
            loop_cmd = bank[offset]
            offset += 1
            commands.append(process_loop_cmd(loop_cmd))
        elif commandbyte == 0xF0:
            duration = bank[offset]
            offset += 1
            commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_FOR_DURATION", "operands": {"duration": duration}, "description": f"Set note length to {duration} and wait for {duration} ticks"})
        elif (commandbyte & 0x7F) == 0x70:
            if commandbyte > 0x7F:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PAUSE_SET_DUR", "operands": {"note": "PAUSE", "duration": duration}, "description": f"Pause and set new note duration to {duration:02X} ticks"})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PAUSE", "operands": {"note": "PAUSE"}, "description": "Pause for note length"})
        elif commandbyte < 8 or commandbyte in range(0x80, 0x88):
            freq = commandbyte & 3
            feedback = (commandbyte >> 2) & 1
            length_set = (commandbyte > 0x7F)
            if length_set:
                duration = bank[offset]
                offset += 1
                commands.append({"bytes": bank[offset-2:offset], "command": "PLAY_NOISE_SET_DUR", "operands": {"frequency": freq, "feedback": feedback, "duration": duration}, "description": f"Play noise frequency {freq} with feedback {feedback} and set new note duration to {duration:02X}."})
            else:
                commands.append({"bytes": bytes([commandbyte]), "command": "PLAY_NOISE", "operands": {"frequency": freq, "feedback": feedback}, "description": f"Play noise frequency {freq} with feedback {feedback} with current duration."})
        else:
            commands.append({"bytes": bytes([commandbyte]), "command": "UNKNOWN_CMD", "operands": {"command": commandbyte}, "description": f"Unknown command byte {commandbyte:02X}"})
    return commands

def process_channel(channel, bank, offset):
    if channel.startswith("YM"):
        return process_ym_channel(offset, bank)
    elif channel == "DAC":
        return process_dac_channel(offset, bank)
    elif channel == "PSGN":
        return process_psgn_channel(offset, bank)
    elif channel.startswith("PSG"):
        return process_psg_channel(offset, bank)
    else:
        print(f" Unknown channel type {channel}")

def process_all_channels(channel_list, bank, ptr, apply_offset=False):
    channels = {}
    for i, channel in enumerate(channel_list):
        offset = int.from_bytes(bank[ptr + i * 2:ptr + i * 2 + 2], "little") - (BANK_OFFSET if apply_offset else 0)
        channels.update({channel: process_channel(channel, bank, offset)})
    return channels

def dump_channel(channel, data, file):
    if(len(data) > 1 or data[0]["command"] != "END"):
        file.write(f"- {channel}:\n")
        for command in data:
            file.write(f"  - {command['command'] + ':':20} {str(command['operands']):60}   # {command['bytes'].hex().upper():8}: {command['description']}\n")

def dump_channels(channels, file):
    file.write("channels:\n")
    for channel_name, channel_data in channels.items():
        dump_channel(channel_name, channel_data, file)

def dump_sfx(sfx_data, filename):
    with open(filename, 'w') as f:
        f.write(f"type: {sfx_data['type']}\n")
        dump_channels(sfx_data["channels"], f)

def dump_music(music_data, filename):
    with open(filename, 'w') as f:
        f.write(f"type: {music_data['type']}\n")
        f.write(f"ym6_mode: {music_data['ym6_mode']}\n")
        f.write(f"ym_timer_b: {music_data['ym_timerb']}\n")
        dump_channels(music_data["channels"], f)

def dump_all_bank_audio(data, prefix, track_offset, dump_function):
    offsets = set()
    for i, item in enumerate(data):
        if item["offset"] in offsets:
            continue
        offsets.add(item["offset"])
        filename = f"{prefix}_{i + track_offset:02d}.yaml"
        dump_function(item, filename)

def get_pcm_sample_table(drv):
    # PCM File offsets located in the driver
    PCM_TABLE_OFFSET = 0x14D4
    pcm_samples = []
    for i in range(24):
        table_line_offset = PCM_TABLE_OFFSET + i * 8
        pcm_samples += [{
            "sample_rate": int(3579545 / (209 + 13 * int(drv[table_line_offset])) + 0.5),
            "reserved": drv[table_line_offset + 1],
            "bank": drv[table_line_offset + 2],
            "reserved2": drv[table_line_offset + 3],
            "length": int.from_bytes(drv[table_line_offset + 4:table_line_offset + 6], "little"),
            "start_offset": int.from_bytes(drv[table_line_offset + 6:table_line_offset + 8], "little") - 0x8000,
        }]
    return pcm_samples

def get_pcm_samples(drv, banks):
    pcm_samples = get_pcm_sample_table(drv)
    samples = []
    for sample in pcm_samples:
        start = sample["start_offset"]
        end = start + sample["length"]
        samples.append(banks[sample["bank"]][start:end])
    return samples

def dump_pcm_wav(sample, filename, sample_rate):
    p = pyaudio.PyAudio()
    with open(filename, 'wb') as wf:
        with wave.open(wf, 'wb') as writer:
            writer.setnchannels(1)
            writer.setsampwidth(1)
            writer.setframerate(sample_rate)
            writer.writeframes(sample)
    p.terminate()

def play_pcm_sample(sample, sample_rate):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paUInt8,
                    channels=1,
                    rate=int(sample_rate),
                    output=True)
    stream.write(sample)
    stream.stop_stream()
    stream.close()
    p.terminate()

def dump_all_pcm(pcm_sample_table, pcm_sample_data):
    with open("pcm_samples.yaml", 'w') as f:
        yaml.dump(pcm_sample_table, f)
    for i, sample in enumerate(pcm_sample_data):
        filename = f"sample_{i:02d}.wav"
        dump_pcm_wav(sample, filename, pcm_sample_table[i]["sample_rate"])

def get_all_sfx(offset, count, bank):
    sfx_ptrs = [int.from_bytes(bank[offset + i * 2:offset + i * 2 + 2], "little") for i in range(count)]
    sfx_data = []
    for sfx_ptr in sfx_ptrs:
        type = bank[sfx_ptr]
        channels = process_all_channels(TYPE_1_CHANNELS if type == 1 else TYPE_2_CHANNELS, bank, sfx_ptr + 1)
        sfx_data.append({"type": type, "offset": sfx_ptr, "channels": channels})
    return sfx_data

def get_all_music(offset, count, bank):
    music_ptrs = [int.from_bytes(bank[offset + i * 2:offset + i * 2 + 2], "little") - BANK_OFFSET for i in range(count)]
    music_data = []
    for music_ptr in music_ptrs:
        type = bank[music_ptr]
        ym6_mode = bank[music_ptr + 1]
        ym_timerb = bank[music_ptr + 3]
        channels = process_all_channels(TYPE_1_CHANNELS if ym6_mode > 0 else TYPE_1A_CHANNELS, bank, music_ptr + 4, True)
        music_data.append({"type": type, "offset": music_ptr, "ym6_mode": ym6_mode, "ym_timerb": ym_timerb, "channels": channels})
    return music_data


with open(ROM_FILE, "rb") as f:
    rom_data = f.read()
print(f"Loaded ROM file '{ROM_FILE}' of size {len(rom_data)} bytes.")

bank1 = rom_data[BANK1_BEGIN:BANK1_END]
bank2 = rom_data[BANK2_BEGIN:BANK2_END]
bank3 = rom_data[BANK3_BEGIN:BANK3_END]
drv   = rom_data[DRV_BEGIN:DRV_END]
bank4 = rom_data[BANK4_BEGIN:BANK4_END]
BANKS = [bank1, bank2, bank3, bank4]

pcm_sample_table = get_pcm_sample_table(drv)
pcm_sample_data = get_pcm_samples(drv, BANKS)

dump_all_pcm(pcm_sample_table, pcm_sample_data)

print("Extracted PCM samples:")
print(pcm_sample_table)
for i, sample in enumerate(pcm_sample_data):
    print(f"Sample {i}: {len(sample)} bytes at rate {pcm_sample_table[i]['sample_rate']} Hz, duration {len(sample)/pcm_sample_table[i]['sample_rate']:.2f} seconds")
    # Play the sample using PyAudio
    play_pcm_sample(sample, pcm_sample_table[i]['sample_rate'])

sfx_data = get_all_sfx(SFX_TABLE_OFFSET, NUM_SFX, drv)
dump_all_bank_audio(sfx_data, "sfx", 0, dump_sfx)
bank3_data = get_all_music(BANK3_TABLE_OFFSET, NUM_BANK3_TRACKS, bank3)
dump_all_bank_audio(bank3_data, "music", 0, dump_music)
bank4_data = get_all_music(BANK4_TABLE_OFFSET, NUM_BANK4_TRACKS, bank4)
dump_all_bank_audio(bank4_data, "music", 32, dump_music)


for i in range(64):
    psg_freq_input = int.from_bytes(drv[0x114b + i * 2:0x114b + i * 2 + 2],"little")
    psg_freq = 3579545 / (32 * psg_freq_input)
    print(f"PSG Frequency Table Entry {i:02} ({NOTES[i + 0x15]}): Input {psg_freq_input}, Frequency {psg_freq:.2f} Hz")
