"""Checks for the ARM64 Image header inside the vendor legacy wrapper."""
import struct


def validate_arm64(payload):
    if len(payload) < 64 or payload[56:60] != b'ARM\x64':
        raise ValueError('Missing ARM64 Image header')
    code0, code1 = struct.unpack_from('<II', payload)
    offset, size, flags, res2, res3, res4 = struct.unpack_from('<6Q', payload, 8)
    if code0 & 0xfc000000 != 0x14000000 or code1:
        raise ValueError('ARM64 header must branch to entry code')
    target = (code0 & 0x03ffffff) * 4
    if not 64 <= target < len(payload):
        raise ValueError('Entry branch leaves the payload')
    if offset != 0 or size < len(payload) or size > 0x1000000:
        raise ValueError('Invalid fixed-load offset or runtime size')
    if flags or res2 or res3 or res4 or payload[60:64] != b'\0' * 4:
        raise ValueError('Unsupported ARM64 header flags or reserved fields')
    return size
