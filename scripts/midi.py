import yaml
import rtmidi
import time
import glob
import pyaudio
import wave

samples = []

def note_to_midi(note):
    note_map = {
        "C ": 0,
        "C#": 1,
        "D ": 2,
        "D#": 3,
        "E ": 4,
        "F ": 5,
        "F#": 6,
        "G ": 7,
        "G#": 8,
        "A ": 9,
        "A#": 10,
        "B ": 11,
        "PAUSE": None
    }
    if note == "PAUSE" or note.startswith("SAMPLE_"):
        return note
    pitch = note[:-1]
    octave = int(note[-1])
    midi_number = (octave + 2) * 12 + note_map[pitch]
    return midi_number

def merge_channels(channels):
    merged = []
    pointers = [0] * len(channels)
    deltas = [0] * len(channels)

    while True:
        next_events = []
        for i, channel in enumerate(channels):
            if pointers[i] < len(channel):
                cmd, delta = channel[pointers[i]]
                next_events.append((delta, i, cmd))
        if not next_events:
            break
        next_events.sort()
        next_delta, chan_idx, cmd = next_events[0]
        for i in range(len(channels)):
            if pointers[i] < len(channels[i]):
                _, delta = channels[i][pointers[i]]
                deltas[i] += next_delta - deltas[i]
        merged.append((cmd, next_delta))
        pointers[chan_idx] += 1
    return merged

def get_midi_cmds(data):
    note_duration = 1
    velocity = 112
    channels = []

    channel_idx = 0
    if "channels" not in data:
        return []
    for channel in data['channels']:
        channel_idx += 1
        notes = []
        for channel_name, channel_data in channel.items():
            delta = 0
            for command_data in channel_data:
                for command, operands in command_data.items():
                    if command == "SET_NOTE_LENGTH":
                        note_duration = operands['duration']
                        delta += note_duration
                    elif "note" in operands and channel_name != "DAC":
                        midi_note = note_to_midi(operands['note'])
                        note_duration = operands.get('duration', note_duration)
                        if midi_note == "PAUSE":
                            delta += note_duration
                        else:
                            notes.append((rtmidi.MidiMessage.noteOn(channel_idx, midi_note, velocity), delta))
                            delta += note_duration
                            notes.append((rtmidi.MidiMessage.noteOff(channel_idx, midi_note), delta))
                    elif "level" in operands:
                        velocity = int(operands['level'] * 127 / 15)
        channels.append(notes)
    return merge_channels(channels)

def play_midi(notes, tick=0.02, samples=samples):
    p = pyaudio.PyAudio()
    out = rtmidi.RtMidiOut()
    available_ports = out.getPortCount()
    print("Available MIDI output ports:")
    for i in range(available_ports):
        print(f"{i}: {out.getPortName(i)}")
    out.openPort(0)

    time.sleep(0.1)
    counter = 0
    cur_delta = 0
    for cmd, delta in notes:
        if delta > cur_delta:
            time.sleep((delta - cur_delta) * tick)
            cur_delta = delta
        print(f"{counter:04d}/{len(notes):04d} delta={cur_delta}: Sending MIDI command: {cmd}")
        out.sendMessage(cmd)
        counter += 1

    time.sleep(tick * 5)
    out.closePort()

for filename in glob.glob("sample_*.wav"):
    print(f"Loading {filename}...")
    with wave.open(filename, 'rb') as wf:
        print(f"Sample rate: {wf.getframerate()}, Channels: {wf.getnchannels()}, Sample width: {wf.getsampwidth()}")
        samples.append({"data": wf.readframes(wf.getnframes()), "sample_rate": wf.getframerate(), "channels": wf.getnchannels(), "sample_width": wf.getsampwidth()})

for filename in glob.glob("*.yaml"):
    print(f"Playing {filename}...")
    with open(filename) as f:
        data = yaml.safe_load(f)
    if "ym_timer_b" in data:
        tick_rate = data['ym_timer_b'] / 10000.0
    else:
        tick_rate = 0.02
    play_midi(get_midi_cmds(data), tick=tick_rate)
    time.sleep(1)