"""Read libretro-database .rdb files: msgpack maps behind a 16-byte RARCHDB header."""
import struct
from typing import Any, Dict, Iterator, Optional, Tuple

MAGIC = b"RARCHDB\0"


def _decode(buf: memoryview, pos: int) -> Tuple[Any, int]:
    b = buf[pos]
    pos += 1
    if b <= 0x7F:
        return b, pos
    if b >= 0xE0:
        return b - 0x100, pos
    if 0x80 <= b <= 0x8F:
        return _map(buf, pos, b & 0x0F)
    if 0x90 <= b <= 0x9F:
        return _array(buf, pos, b & 0x0F)
    if 0xA0 <= b <= 0xBF:
        n = b & 0x1F
        return _text(bytes(buf[pos:pos + n])), pos + n
    if b == 0xC0:
        return None, pos
    if b == 0xC2:
        return False, pos
    if b == 0xC3:
        return True, pos
    if b in (0xC4, 0xC5, 0xC6):
        w = {0xC4: 1, 0xC5: 2, 0xC6: 4}[b]
        n = int.from_bytes(buf[pos:pos + w], "big")
        pos += w
        return bytes(buf[pos:pos + n]), pos + n
    if b == 0xCA:
        return struct.unpack_from(">f", buf, pos)[0], pos + 4
    if b == 0xCB:
        return struct.unpack_from(">d", buf, pos)[0], pos + 8
    if b in (0xCC, 0xCD, 0xCE, 0xCF):
        w = {0xCC: 1, 0xCD: 2, 0xCE: 4, 0xCF: 8}[b]
        return int.from_bytes(buf[pos:pos + w], "big"), pos + w
    if b in (0xD0, 0xD1, 0xD2, 0xD3):
        w = {0xD0: 1, 0xD1: 2, 0xD2: 4, 0xD3: 8}[b]
        return int.from_bytes(buf[pos:pos + w], "big", signed=True), pos + w
    if b in (0xD9, 0xDA, 0xDB):
        w = {0xD9: 1, 0xDA: 2, 0xDB: 4}[b]
        n = int.from_bytes(buf[pos:pos + w], "big")
        pos += w
        return _text(bytes(buf[pos:pos + n])), pos + n
    if b in (0xDC, 0xDD):
        w = {0xDC: 2, 0xDD: 4}[b]
        n = int.from_bytes(buf[pos:pos + w], "big")
        return _array(buf, pos + w, n)
    if b in (0xDE, 0xDF):
        w = {0xDE: 2, 0xDF: 4}[b]
        n = int.from_bytes(buf[pos:pos + w], "big")
        return _map(buf, pos + w, n)
    raise ValueError("unhandled msgpack byte {:#x} at {}".format(b, pos - 1))


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _map(buf: memoryview, pos: int, n: int) -> Tuple[Dict[Any, Any], int]:
    out = {}
    for _ in range(n):
        k, pos = _decode(buf, pos)
        v, pos = _decode(buf, pos)
        out[k] = v
    return out, pos


def _array(buf: memoryview, pos: int, n: int) -> Tuple[list, int]:
    out = []
    for _ in range(n):
        v, pos = _decode(buf, pos)
        out.append(v)
    return out, pos


def records(path: str) -> Iterator[Dict[str, Any]]:
    """Yield every record map in the file."""
    with open(path, "rb") as f:
        buf = memoryview(f.read())
    if bytes(buf[:8]) != MAGIC:
        raise ValueError("{}: not an RDB file".format(path))
    meta_off = struct.unpack_from(">Q", buf, 8)[0]
    pos = 16
    end = meta_off if meta_off else len(buf)
    while pos < end:
        rec, pos = _decode(buf, pos)
        if rec is None:
            break
        if isinstance(rec, dict):
            yield rec


def hexfield(rec: Dict[str, Any], key: str) -> Optional[str]:
    """A hash field as lower-case hex, or None when absent."""
    v = rec.get(key)
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, str):
        return v.lower()
    return None


def textfield(rec: Dict[str, Any], key: str) -> str:
    """A text field, decoding the byte strings the database uses for serials."""
    v = rec.get(key)
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("ascii", "replace").strip()
    if v is None:
        return ""
    return str(v).strip()
