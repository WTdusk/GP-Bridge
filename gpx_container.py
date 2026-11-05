"""Decode the BCFS filesystem and BCFZ bit stream used by Guitar Pro 6.

Format reference: alphaTab's GpxFileSystem and BitReader (MPL-2.0),
https://github.com/CoderLine/alphaTab/tree/develop/packages/alphatab/src/importer
This module implements the container layout directly; no external runtime needed.
"""
import struct

MAX_CONTAINER = 128 * 1024 * 1024


def decompress_bcfz(raw: bytes) -> bytes:
    if len(raw) < 8:
        raise ValueError("Truncated BCFZ header")
    expected = struct.unpack_from("<I", raw, 4)[0]
    if not 4 <= expected <= MAX_CONTAINER:
        raise ValueError("Invalid BCFZ decompressed size")
    position = 64

    def bits(count, reverse=False):
        nonlocal position
        if position + count > len(raw) * 8:
            raise ValueError("Truncated BCFZ compressed stream")
        result = 0
        for index in range(count):
            bit = (raw[position // 8] >> (7 - position % 8)) & 1
            result |= bit << (index if reverse else count - index - 1)
            position += 1
        return result

    output = bytearray()
    try:
        while len(output) < expected:
            if bits(1):
                width = bits(4)
                distance, count = bits(width, True), bits(width, True)
                count = min(distance, count)
                if distance > len(output) or not count:
                    raise ValueError("Invalid BCFZ back reference")
                start = len(output) - distance
                output.extend(output[start:start + count])
            else:
                output.extend(bits(8) for _ in range(bits(2, True)))
    except ValueError as exc:
        # GP6 writers can omit unused filesystem padding at EOF. Actual file
        # sizes and sectors are checked when extracting the score below.
        if "Truncated BCFZ compressed stream" not in str(exc):
            raise
    return bytes(output)


def extract_gpif(raw: bytes) -> bytes:
    if raw.startswith(b"BCFZ"):
        raw = decompress_bcfz(raw)
    if not raw.startswith(b"BCFS"):
        raise ValueError("GPX container has no BCFS filesystem")
    data = memoryview(raw)[4:]
    sector_size = 4096
    for offset in range(sector_size, len(data), sector_size):
        if offset + 0x98 > len(data):
            break
        if struct.unpack_from("<I", data, offset)[0] != 2:
            continue
        name = bytes(data[offset + 4:offset + 131]).split(b"\0", 1)[0].decode("utf-8", "replace")
        if not name.lower().endswith(".gpif"):
            continue
        size = struct.unpack_from("<I", data, offset + 0x8c)[0]
        if size > len(data):
            raise ValueError("GPIF entry has an invalid size")
        result = bytearray()
        for pointer in range(offset + 0x94, offset + sector_size, 4):
            sector = struct.unpack_from("<I", data, pointer)[0]
            if not sector:
                if len(result) < size:
                    raise ValueError("Truncated GPIF sector list")
                return bytes(result[:size])
            start = sector * sector_size
            if start + sector_size > len(data):
                raise ValueError("GPIF sector is outside the GPX container")
            result.extend(data[start:start + sector_size])
        raise ValueError("Unterminated GPIF sector list")
    raise ValueError("GPX container contains no score.gpif")
