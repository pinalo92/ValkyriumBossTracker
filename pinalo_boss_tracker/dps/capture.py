"""Copia local del TCP del juego con Npcap. No envía nada al servidor."""

from __future__ import annotations

import ctypes
import struct
import threading
from ctypes import POINTER, c_char_p, c_int, c_long, c_uint, c_ubyte, c_void_p
from pathlib import Path

from .protocol import FrameBuffer, parse_message
from .session import CombatSession

_GAME_PORT = 13328


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", c_long), ("tv_usec", c_long)]


class _PktHdr(ctypes.Structure):
    _fields_ = [("ts", _Timeval), ("caplen", c_uint), ("len", c_uint)]


class _PcapIf(ctypes.Structure):
    pass


_PcapIf._fields_ = [
    ("next", POINTER(_PcapIf)),
    ("name", c_char_p),
    ("description", c_char_p),
    ("addresses", c_void_p),
    ("flags", c_uint),
]


def _wpcap_path() -> Path | None:
    import os

    root = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for candidate in (
        root / "System32" / "Npcap" / "wpcap.dll",
        root / "System32" / "wpcap.dll",
    ):
        if candidate.is_file():
            return candidate
    return None


class _Flow:
    def __init__(self) -> None:
        self.next_seq: int | None = None
        self.frames = FrameBuffer()

    def push(self, seq: int, payload: bytes) -> list[bytes]:
        if not payload:
            return []
        if self.next_seq is None:
            self.next_seq = (seq + len(payload)) & 0xFFFFFFFF
            return self.frames.push(payload)
        if seq == self.next_seq:
            self.next_seq = (seq + len(payload)) & 0xFFFFFFFF
            return self.frames.push(payload)
        # Hueco o retransmisión: realinear. Se pierde como mucho la trama a medias.
        if ((seq - self.next_seq) & 0xFFFFFFFF) < 0x80000000:
            self.next_seq = (seq + len(payload)) & 0xFFFFFFFF
            self.frames = FrameBuffer()
            return self.frames.push(payload)
        return []


def _tcp_payloads(packet: bytes, link_type: int) -> list[tuple[tuple, int, bytes]]:
    if link_type == 1 and len(packet) >= 14:
        ethertype = struct.unpack_from("!H", packet, 12)[0]
        ip_off = 14
        if ethertype == 0x8100 and len(packet) >= 18:
            ethertype = struct.unpack_from("!H", packet, 16)[0]
            ip_off = 18
    elif link_type in (12, 101, 0, 14):
        ethertype = 0x0800 if packet and (packet[0] >> 4) == 4 else 0x86DD
        ip_off = 0
    else:
        return []
    if ethertype == 0x0800:
        return _ipv4(packet, ip_off)
    if ethertype == 0x86DD:
        return _ipv6(packet, ip_off)
    return []


def _ipv4(packet: bytes, off: int) -> list[tuple[tuple, int, bytes]]:
    if off + 20 > len(packet):
        return []
    ver_ihl = packet[off]
    if ver_ihl >> 4 != 4:
        return []
    ihl = (ver_ihl & 0x0F) * 4
    if ihl < 20 or off + ihl > len(packet):
        return []
    if packet[off + 9] != 6:
        return []
    src = packet[off + 12 : off + 16]
    dst = packet[off + 16 : off + 20]
    return _tcp(packet, off + ihl, src, dst)


def _ipv6(packet: bytes, off: int) -> list[tuple[tuple, int, bytes]]:
    if off + 40 > len(packet) or (packet[off] >> 4) != 6:
        return []
    if packet[off + 6] != 6:
        return []
    src = packet[off + 8 : off + 24]
    dst = packet[off + 24 : off + 40]
    return _tcp(packet, off + 40, src, dst)


def _tcp(packet: bytes, off: int, src: bytes, dst: bytes) -> list[tuple[tuple, int, bytes]]:
    if off + 20 > len(packet):
        return []
    sport, dport = struct.unpack_from("!HH", packet, off)
    if sport != _GAME_PORT and dport != _GAME_PORT:
        return []
    seq = struct.unpack_from("!I", packet, off + 4)[0]
    offset = ((packet[off + 12] >> 4) & 0x0F) * 4
    if offset < 20 or off + offset > len(packet):
        return []
    payload = packet[off + offset :]
    if not payload:
        return []
    key = (src, sport, dst, dport)
    return [(key, seq, payload)]


class NpcapCapture:
    def __init__(self, session: CombatSession) -> None:
        self.session = session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="valkyrium-dps", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        dll_path = _wpcap_path()
        if dll_path is None:
            self.session.set_status("Instala Npcap (npcap.com) para el medidor", listening=False)
            return
        try:
            lib = ctypes.WinDLL(str(dll_path))
        except OSError as exc:
            self.session.set_status(f"Npcap no cargó ({exc})", listening=False)
            return
        self._bind(lib)
        devices = self._devices(lib)
        if not devices:
            self.session.set_status("Npcap no ve tarjetas de red", listening=False)
            return
        opened = 0
        handles = []
        for name in devices:
            err = ctypes.create_string_buffer(256)
            handle = lib.pcap_open_live(name, 65535, 1, 80, err)
            if not handle:
                continue
            program = ctypes.create_string_buffer(256)
            # bpf_program is { uint bf_len; bpf_insn *bf_insns }. Two pointers-worth is enough scratch.
            filt = ctypes.create_string_buffer(64)
            if lib.pcap_compile(handle, filt, b"tcp", 1, 0xFFFFFFFF) != 0:
                lib.pcap_close(handle)
                continue
            if lib.pcap_setfilter(handle, filt) != 0:
                lib.pcap_close(handle)
                continue
            link = lib.pcap_datalink(handle)
            handles.append((handle, link))
            opened += 1
            _ = program
        if not handles:
            self.session.set_status(
                "Npcap está, pero hace falta permiso. Desmarca «solo administradores» al instalarlo.",
                listening=False,
            )
            return
        self.session.set_status("Escuchando el juego", listening=True)
        flows: dict[tuple, _Flow] = {}
        hdr_ptr = POINTER(_PktHdr)()
        data_ptr = POINTER(c_ubyte)()
        while not self._stop.is_set():
            got = False
            for handle, link in handles:
                rc = lib.pcap_next_ex(handle, ctypes.byref(hdr_ptr), ctypes.byref(data_ptr))
                if rc != 1 or not hdr_ptr or not data_ptr:
                    continue
                got = True
                caplen = int(hdr_ptr.contents.caplen)
                raw = ctypes.string_at(data_ptr, caplen)
                for key, seq, payload in _tcp_payloads(raw, link):
                    flow = flows.get(key)
                    if flow is None:
                        if len(flows) > 64:
                            flows.clear()
                        flow = _Flow()
                        flows[key] = flow
                    for message in flow.push(seq, payload):
                        hit, player = parse_message(message)
                        if player:
                            self.session.rename(player.entity_id, player.name, player.you)
                        if hit:
                            self.session.add_hit(hit.actor_id, hit.target_id, hit.damage, hit.heal)
            if not got:
                self._stop.wait(0.02)
        for handle, _link in handles:
            try:
                lib.pcap_close(handle)
            except Exception:
                pass

    def _bind(self, lib: ctypes.WinDLL) -> None:
        lib.pcap_findalldevs.argtypes = [POINTER(POINTER(_PcapIf)), c_char_p]
        lib.pcap_findalldevs.restype = c_int
        lib.pcap_freealldevs.argtypes = [POINTER(_PcapIf)]
        lib.pcap_open_live.argtypes = [c_char_p, c_int, c_int, c_int, c_char_p]
        lib.pcap_open_live.restype = c_void_p
        lib.pcap_compile.argtypes = [c_void_p, c_void_p, c_char_p, c_int, c_uint]
        lib.pcap_compile.restype = c_int
        lib.pcap_setfilter.argtypes = [c_void_p, c_void_p]
        lib.pcap_setfilter.restype = c_int
        lib.pcap_datalink.argtypes = [c_void_p]
        lib.pcap_datalink.restype = c_int
        lib.pcap_next_ex.argtypes = [c_void_p, POINTER(POINTER(_PktHdr)), POINTER(POINTER(c_ubyte))]
        lib.pcap_next_ex.restype = c_int
        lib.pcap_close.argtypes = [c_void_p]

    def _devices(self, lib: ctypes.WinDLL) -> list[bytes]:
        err = ctypes.create_string_buffer(256)
        first = POINTER(_PcapIf)()
        if lib.pcap_findalldevs(ctypes.byref(first), err) != 0 or not first:
            return []
        names: list[bytes] = []
        node = first
        while node:
            item = node.contents
            if item.name and not (item.flags & 0x00000001):
                names.append(item.name)
            if not item.next:
                break
            node = item.next
        lib.pcap_freealldevs(first)
        return names
