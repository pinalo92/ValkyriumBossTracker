"""Lectura del flujo de combate que el servidor ya envía al cliente.

Trocea tramas con prefijo varint, descomprime lotes LZ4 y saca golpes y nombres.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

TAG_DAMAGE = (0x04, 0x38)
TAG_DOT = (0x05, 0x38)
TAG_SELF = (0x33, 0x36)
TAG_OTHER = (0x45, 0x36)
SYNC = bytes((0x06, 0x00, 0x36))

_SKILL_RANGES = (
    (11_000_000, 20_000_000),
    (1_000_000, 10_000_000),
    (100_000, 200_000),
    (29_000_000, 31_000_000),
)
_TRAILER = (0, 0, 0, 0, 8, 12, 10, 14)
_MAX_MSG = 2_000_000
_MAX_BUF = 4_000_000


def read_varint(data: bytes | bytearray, pos: int, end: int) -> tuple[int | None, int]:
    """Devuelve (valor, nueva posición). valor None si falta bytes o se desborda."""
    value = 0
    shift = 0
    while pos < end and shift <= 28:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, pos
        shift += 7
    return None, pos


def _skip_varint(data: bytes | bytearray, pos: int, end: int) -> int:
    while pos < end and (data[pos] & 0x80) != 0:
        pos += 1
    if pos < end:
        pos += 1
    return pos


def _skill_ok(code: int) -> bool:
    return any(lo <= code < hi for lo, hi in _SKILL_RANGES)


def _take_skill(data: bytes | bytearray, pos: int, end: int) -> tuple[int, int] | None:
    for i in range(7):
        if pos + i + 4 > end:
            break
        raw = struct.unpack_from("<i", data, pos + i)[0]
        if raw <= 0:
            continue
        if _skill_ok(raw) or _skill_ok(raw // 100):
            return raw, pos + i + 5
    return None


def _index_tag(data: bytes | bytearray, start: int, end: int, tag: tuple[int, int]) -> int:
    a, b = tag
    for i in range(start, end - 1):
        if data[i] == a and data[i + 1] == b:
            return i
    return -1


def _read_name(data: bytes | bytearray, start: int, end: int) -> tuple[str, int] | None:
    limit = min(start + 10, end)
    for i in range(start, limit):
        if data[i] != 7:
            continue
        length, pos = read_varint(data, i + 1, end)
        if length is None or length < 1 or length > 72 or pos + length > end:
            return None
        raw = bytes(data[pos : pos + length])
        name = raw.decode("utf-8", errors="replace").strip("\x00 ").strip()
        if not name or name.isdigit():
            return None
        return name, pos + length
    return None


@dataclass(frozen=True)
class Hit:
    actor_id: int
    target_id: int
    damage: int
    heal: int


@dataclass(frozen=True)
class PlayerName:
    entity_id: int
    name: str
    you: bool


def parse_damage(data: bytes | bytearray, offset: int, length: int) -> Hit | None:
    end = offset + length
    pos = offset
    consumed = 0
    while pos < end:
        idx = pos
        pos += 1
        consumed += 1
        if (data[idx] & 0x80) == 0:
            if end - pos <= 1 or data[pos] != TAG_DAMAGE[0] or data[pos + 1] != TAG_DAMAGE[1]:
                return None
            pos += 2
            break
        if consumed > 5:
            return None
    else:
        return None

    target, pos = read_varint(data, pos, end)
    flags, pos = read_varint(data, pos, end)
    if target is None or flags is None:
        return None
    category = flags & 0xF
    if category < 4 or category > 7:
        return None
    pos = _skip_varint(data, pos, end)
    actor, pos = read_varint(data, pos, end)
    if actor is None or actor == target or end - pos < 5:
        return None
    skill = _take_skill(data, pos, end)
    if skill is None:
        return None
    _, pos = skill
    damage_type, pos = read_varint(data, pos, end)
    if damage_type is None:
        return None

    flag_adjust = 0
    if end - pos > 1 and (pos + 2 >= end or data[pos + 1] == 0):
        pos += 2
        flag_adjust = 1
    trailer = _TRAILER[category] - flag_adjust * 2
    if trailer > 0:
        if pos + trailer > end:
            return None
        pos += trailer
    pos = _skip_varint(data, pos, end)
    damage, pos = read_varint(data, pos, end)
    if damage is None:
        damage = 0

    if end - pos >= 2:
        count, hit_pos = read_varint(data, pos, end)
        if count is not None and 0 < count < 100:
            total = 0
            cursor = hit_pos
            ok = True
            for _ in range(count):
                piece, cursor = read_varint(data, cursor, end)
                if piece is None:
                    ok = False
                    break
                total += piece
            if ok and total > 0 and (damage == 0 or total >= damage * 0.005):
                reduced = damage - total
                damage = reduced if reduced > 0 else 0
                pos = cursor

    heal = 0
    if end - pos > 1 and data[pos] == 3 and (pos + 1 >= end or data[pos + 1] == 0):
        heal_val, _ = read_varint(data, pos + 2, end)
        if heal_val:
            heal = heal_val
    if damage <= 0 and heal <= 0:
        return None
    return Hit(int(actor), int(target), int(damage), int(heal))


def parse_dot(data: bytes | bytearray, offset: int, length: int) -> Hit | None:
    end = offset + length
    pos = offset
    while pos < end:
        if (data[pos] & 0x80) == 0:
            pos += 1
            break
        pos += 1
        if pos - offset > 5:
            return None
    else:
        return None
    if pos + 1 >= end or data[pos] != TAG_DOT[0] or data[pos + 1] != TAG_DOT[1]:
        return None
    pos += 2
    target, pos = read_varint(data, pos, end)
    if target is None or pos >= end:
        return None
    has_extra = (data[pos] & 2) != 0
    pos += 1
    actor, pos = read_varint(data, pos, end)
    heal, pos = read_varint(data, pos, end)
    if actor is None or heal is None or pos + 4 > end:
        return None
    pos += 4
    damage = 0
    if has_extra:
        damage_val, pos = read_varint(data, pos, end)
        if damage_val is None:
            return None
        damage = damage_val
    if actor == target and damage:
        return None
    if damage <= 0 and heal <= 0:
        return None
    return Hit(int(actor), int(target), int(damage), int(heal))


def parse_player(data: bytes | bytearray, offset: int, length: int) -> PlayerName | None:
    end = offset + length
    self_at = _index_tag(data, offset, end, TAG_SELF)
    if self_at >= 0:
        entity, pos = read_varint(data, self_at + 2, end)
        if entity is not None:
            found = _read_name(data, pos, end)
            if found:
                return PlayerName(int(entity), found[0], True)

    other_at = _index_tag(data, offset, end, TAG_OTHER)
    if other_at < 0:
        return None
    pos = other_at + 2
    entity, pos = read_varint(data, pos, end)
    if entity is None:
        return None
    pos = _skip_varint(data, pos, end)
    pos = _skip_varint(data, pos, end)
    found = _read_name(data, pos, end)
    if not found:
        return None
    return PlayerName(int(entity), found[0], False)


def parse_message(data: bytes | bytearray, offset: int = 0, length: int | None = None) -> tuple[Hit | None, PlayerName | None]:
    if length is None:
        length = len(data) - offset
    if length < 4 or length == 11:
        return None, None
    return parse_damage(data, offset, length) or parse_dot(data, offset, length), parse_player(data, offset, length)


def _lz4(src: bytes, size: int) -> bytes | None:
    if size <= 0 or size > _MAX_MSG:
        return None
    try:
        import lz4.block
    except ImportError:
        return None
    try:
        return lz4.block.decompress(src, uncompressed_size=size)
    except Exception:
        return None


class FrameBuffer:
    """Junta el TCP ya ordenado y suelta mensajes de combate."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def push(self, chunk: bytes) -> list[bytes]:
        if not chunk:
            return []
        if len(self._buf) + len(chunk) > _MAX_BUF:
            self._buf.clear()
        self._buf.extend(chunk)
        out: list[bytes] = []
        i = 0
        buf = self._buf
        while i < len(buf):
            while i < len(buf) and buf[i] == 0:
                i += 1
            if i >= len(buf):
                break
            start = i
            val, after = read_varint(buf, i, len(buf))
            if val is None:
                i = start
                break
            consumed = after - start
            msg_len = val + consumed - 4
            if msg_len <= 0 or msg_len > _MAX_MSG:
                sync = buf.find(SYNC, start + 1)
                if sync < 0:
                    i = len(buf)
                    break
                i = sync
                continue
            if start + msg_len > len(buf):
                i = start
                break
            i = start + msg_len
            if msg_len > consumed:
                out.extend(self._expand(buf[start:i], consumed))
        if i > 0:
            del buf[:i]
        return out

    def _expand(self, frame: bytes, varint_len: int) -> list[bytes]:
        p = varint_len
        if p < len(frame) and (frame[p] & 0xF0) == 0xF0 and frame[p] != 0xFF:
            p += 1
        if p + 2 <= len(frame) and frame[p] == 0xFF and frame[p + 1] == 0xFF:
            if p + 6 > len(frame):
                return []
            size = struct.unpack_from("<i", frame, p + 2)[0]
            plain = _lz4(frame[p + 6 :], size)
            if not plain:
                return []
            return self._expand_block(plain)
        return [bytes(frame)]

    def _expand_block(self, data: bytes) -> list[bytes]:
        out: list[bytes] = []
        i = 0
        end = len(data)
        while i < end:
            while i < end and data[i] == 0:
                i += 1
            if i >= end:
                break
            start = i
            val, after = read_varint(data, i, end)
            if val is None:
                out.append(data[start:end])
                break
            consumed = after - start
            msg_len = val + consumed - 4
            if msg_len <= 0 or start + msg_len > end:
                out.append(data[start:end])
                break
            out.append(data[start : start + msg_len])
            i = start + msg_len
        return out
