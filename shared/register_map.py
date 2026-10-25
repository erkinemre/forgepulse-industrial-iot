"""Case study's fixed Modbus register contract, shown in device configuration."""
REGISTER_MAP = {
    "produced": {"table": "input", "address": 30001, "words": 2, "type": "uint32", "word_order": "ABCD", "scale": 1},
    "temperature_c": {"table": "input", "address": 30003, "words": 2, "type": "float32", "word_order": "CDAB", "scale": 1},
    "current_a": {"table": "input", "address": 30010, "words": 1, "type": "int16", "scale": 0.01},
    "rejected": {"table": "input", "address": 30020, "words": 1, "type": "uint16", "scale": 1},
    "state": {"table": "holding", "address": 40001, "words": 1, "type": "uint16", "scale": 1},
}
