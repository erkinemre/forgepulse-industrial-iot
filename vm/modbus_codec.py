"""PDF register map: zero based offsets for 30001/40001."""
import struct


def encode(belt):
    produced = struct.pack(">I", belt.produced)
    temperature = struct.pack(">f", belt.temperature_c)
    inputs = [0] * 20
    inputs[0:2] = struct.unpack(">HH", produced)       # ABCD
    inputs[2:4] = struct.unpack(">HH", temperature[::-1][::-1])[::-1]  # CDAB word swap
    inputs[9] = round(belt.current_a * 100) & 0xFFFF
    inputs[19] = belt.rejected & 0xFFFF
    return inputs, [belt.state]


def decode(inputs, holding):
    produced = struct.unpack(">I", struct.pack(">HH", *inputs[0:2]))[0]
    temperature = struct.unpack(">f", struct.pack(">HH", *inputs[2:4][::-1]))[0]
    current_raw = inputs[9] if inputs[9] < 0x8000 else inputs[9] - 0x10000
    return {"produced": produced, "temperature_c": temperature,
            "current_a": current_raw / 100, "rejected": inputs[19], "state": holding[0]}
