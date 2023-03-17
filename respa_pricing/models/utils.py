import base64
import struct
import time


def generate_id():
    t = time.time() * 1000000
    b = base64.b32encode(struct.pack(">Q", int(t)).lstrip(b"\x00")).strip(b"=").lower()
    return b.decode("utf8")
