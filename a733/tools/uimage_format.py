"""Legacy image validation and script packing, matching the vendor v59 path."""
import struct
import time
import zlib

FORMAT = '>7I4B32s'
MAGIC = 0x27051956


def validate(data, expected_type):
    if len(data) < 64:
        raise ValueError('Truncated image')
    fields = struct.unpack(FORMAT, data[:64])
    header = data[:4] + b'\0' * 4 + data[8:64]
    payload = data[64:]
    if fields[0] != MAGIC or zlib.crc32(header) & 0xffffffff != fields[1]:
        raise ValueError('Invalid header/magic/CRC')
    if fields[3] != len(payload) or zlib.crc32(payload) & 0xffffffff != fields[6]:
        raise ValueError('Invalid payload length/CRC')
    if fields[7:11] != (5, 2, expected_type, 0):
        raise ValueError('Unexpected vendor legacy image attributes')
    if expected_type == 2 and fields[4:6] != (0x41000000, 0x41000000):
        raise ValueError('Unexpected stage0 load/entry')
    if expected_type == 6:
        size, end = struct.unpack('>II', payload[:8])
        if end or size != len(payload) - 8:
            raise ValueError('Invalid script size table')
    return fields


def script_image(script, name='ios-a733 SAFE MANUAL stage0'):
    encoded_name = name.encode('ascii')
    if len(encoded_name) > 32:
        raise ValueError('Script image name exceeds 32 bytes')
    script = script.replace(b'\r\n', b'\n')
    payload = struct.pack('>II', len(script), 0) + script
    header = struct.pack(FORMAT, MAGIC, 0, int(time.time()), len(payload), 0, 0,
                         zlib.crc32(payload) & 0xffffffff, 5, 2, 6, 0,
                         encoded_name.ljust(32, b'\0'))
    result = header[:4] + struct.pack('>I', zlib.crc32(header) & 0xffffffff) + header[8:] + payload
    validate(result, 6)
    return result
