import struct


def check_elf(data, abi, alignment):
    machines = {"arm64-v8a": (183, 2), "armeabi-v7a": (40, 1), "x86_64": (62, 2)}
    if abi not in machines:
        raise ValueError(f"Unsupported ELF architecture: {abi}")
    if (
        len(data) < 16
        or data[:4] != b"\x7fELF"
        or data[5] != 1
        or data[4] not in (1, 2)
    ):
        raise ValueError("Not a little-endian ELF library")
    wide = data[4] == 2
    if len(data) < (64 if wide else 52):
        raise ValueError("Truncated ELF header")
    machine = struct.unpack_from("<H", data, 18)[0]
    if (machine, data[4]) != machines[abi]:
        raise ValueError(f"Wrong ELF architecture for {abi}")
    offset = struct.unpack_from("<Q" if wide else "<I", data, 32 if wide else 28)[0]
    size, count = struct.unpack_from("<HH", data, 54 if wide else 42)
    if size < (56 if wide else 32) or offset + size * count > len(data):
        raise ValueError("Truncated ELF program headers")
    loads = 0
    for i in range(count):
        start = offset + i * size
        if struct.unpack_from("<I", data, start)[0] != 1:
            continue
        loads += 1
        page = struct.unpack_from(
            "<Q" if wide else "<I", data, start + (48 if wide else 28)
        )[0]
        if page < alignment or page & (page - 1):
            raise ValueError(f"Insufficient ELF alignment for {abi}: {page}")
        file_offset, address = struct.unpack_from(
            "<QQ" if wide else "<II", data, start + (8 if wide else 4)
        )
        if file_offset % alignment != address % alignment:
            raise ValueError(f"Misaligned ELF LOAD segment for {abi}")
    if not loads:
        raise ValueError("ELF contains no LOAD segments")


def check_apk_native(archive, expected_abis, alignment=16384):
    inventory = {}
    for item in archive.infolist():
        if not item.filename.endswith(".so"):
            continue
        parts = item.filename.split("/")
        if len(parts) != 3 or parts[0] != "lib":
            raise ValueError(f"Unexpected native library path: {item.filename}")
        _, abi, name = parts
        libraries = inventory.setdefault(abi, set())
        if name in libraries:
            raise ValueError(f"Duplicate native library: {item.filename}")
        libraries.add(name)
        check_elf(archive.read(item), abi, alignment)
    if set(inventory) != set(expected_abis):
        raise ValueError(
            f"APK native architecture inventory differs: {sorted(inventory)}"
        )
    for abi, libraries in inventory.items():
        if not {"libarboresce_ffi.so", "libjnidispatch.so"} <= libraries:
            raise ValueError(f"APK missing Arboresce or JNA native library: {abi}")
    return {abi: sorted(libraries) for abi, libraries in sorted(inventory.items())}
