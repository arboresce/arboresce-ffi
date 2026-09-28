import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import platform
import re
import stat
import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path, PurePosixPath

SDK = Path(__file__).resolve().parents[2]
SYMBOLS = ["arboresce_v1_abi_version", "arboresce_v1_name", "arboresce_v1_print_name"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def host_target():
    architecture = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64"}.get(
        platform.machine()
    )
    system = {"Darwin": "apple-darwin", "Linux": "unknown-linux-gnu"}.get(
        platform.system()
    )
    if not architecture or not system:
        raise ValueError("No native C package identity for this host")
    return f"{architecture}-{system}"


def library_names():
    if platform.system() == "Darwin":
        return "libarboresce_c.1.dylib", "libarboresce_c.dylib"
    if platform.system() == "Linux":
        return "libarboresce_c.so.1", "libarboresce_c.so"
    raise ValueError("Unsupported C package host")


def source_inputs(sdk):
    names = {
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        "DEVELOPERS.md",
        "scripts/make.sh",
        "scripts/native.sh",
        "tests/consumers/native_packages.py",
    }
    for directory in ("crates/c", "bindings/c", "bindings/cpp"):
        names.update(
            path.relative_to(sdk).as_posix()
            for path in (sdk / directory).rglob("*")
            if path.is_file()
        )
    return {name: digest(regular_file(sdk, name)) for name in sorted(names)}


def identity(sdk):
    cargo = tomllib.loads((sdk / "Cargo.toml").read_text())
    baseline = json.loads((sdk / "bindings/c/tests/abi_v1.json").read_text())
    if baseline.get("abi_version") != 65536 or baseline.get("symbols") != SYMBOLS:
        raise ValueError("C ABI baseline identity differs")
    if cargo["profile"]["c-release"].get("panic") != "unwind":
        raise ValueError("C artifacts require the unwinding profile")
    return {
        "schema": 1,
        "version": cargo["workspace"]["package"]["version"],
        "target": host_target(),
        "core_revision": cargo["workspace"]["dependencies"]["arboresce"]["rev"],
        "compiler_pin": tomllib.loads((sdk / "rust-toolchain.toml").read_text())[
            "toolchain"
        ]["channel"],
        "profile": "c-release",
        "panic": "unwind",
        "relocation_model": "pic",
        "abi": baseline,
        "abi_sha256": digest(sdk / "bindings/c/tests/abi_v1.json"),
        "generated_header_sha256": digest(
            sdk / "bindings/c/include/arboresce/arboresce.h"
        ),
        "inputs": source_inputs(sdk),
    }


def command_output(command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def tool_identity(sdk):
    rust = command_output(["rustc", "-vV"])
    compiler = tomllib.loads((sdk / "rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    if (
        not rust.startswith(f"rustc {compiler} ")
        or f"host: {host_target()}" not in rust.splitlines()
    ):
        raise ValueError("Native C compiler/host differs from pinned identity")
    generator = command_output([str(sdk / "build/tools/bin/cbindgen"), "--version"])
    if generator != "cbindgen 0.29.4":
        raise ValueError("Wrong C header generator")
    return {
        "rust": rust,
        "c": command_output(["cc", "--version"]),
        "cmake": command_output(["cmake", "--version"]).splitlines()[0],
        "generator": generator,
    }


def safe_name(name):
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in name.split("/"))
        or "\\" in name
        or ":" in name
    ):
        raise ValueError(f"Invalid native package path: {name}")
    return path


def regular_file(root, name, aliases=None):
    safe_name(name)
    root = Path(root).resolve()
    path = root / name
    for ancestor in path.parents:
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ValueError(f"Symlinked native package directory: {name}")
    if path.is_symlink():
        expected = (aliases or {}).get(name)
        if (
            not expected
            or os.readlink(path) != expected
            or path.parent / expected == path
        ):
            raise ValueError(f"Invalid native library alias: {name}")
        target = path.parent / expected
        if (
            target.is_symlink()
            or not target.is_file()
            or target.resolve().parent != path.parent
        ):
            raise ValueError(f"Escaping native library alias: {name}")
        return target
    if not path.is_file():
        raise ValueError(f"Missing native package file: {name}")
    return path


def installed_files(kind):
    shared, alias = library_names()
    common = {
        f"share/arboresce-{kind}/{name}"
        for name in ("LICENSE-MIT", "LICENSE-APACHE", "README.md", "DEVELOPERS.md")
    }
    if kind == "c":
        return common | {
            "include/arboresce/arboresce.h",
            "include/arboresce/export.h",
            "lib/libarboresce_c.a",
            f"lib/{shared}",
            f"lib/{alias}",
            "lib/pkgconfig/arboresce.pc",
            *{
                f"lib/cmake/Arboresce/Arboresce{name}.cmake"
                for name in ("Config", "Targets", "ConfigVersion")
            },
        }
    if kind == "cpp":
        return common | {
            "include/arboresce/arboresce.hpp",
            *{
                f"lib/cmake/ArboresceCpp/ArboresceCpp{name}.cmake"
                for name in ("Config", "Targets", "ConfigVersion")
            },
        }
    raise ValueError("Unknown native package")


def manifest_path(kind):
    return f"share/arboresce-{kind}/package.json"


def documentation(sdk, kind):
    return {
        f"share/arboresce-{kind}/DEVELOPERS.md": (sdk / "DEVELOPERS.md").read_bytes(),
        f"share/arboresce-{kind}/README.md": (sdk / "bindings" / kind / "README.md")
        .read_bytes()
        .replace(b"../../DEVELOPERS.md", b"DEVELOPERS.md"),
    }


def archive_files(kind):
    return installed_files(kind) | {
        manifest_path(kind),
        f"share/arboresce-{kind}/abi_v1.json",
    }


def verify_native_artifacts(directory):
    shared, _ = library_names()
    library = regular_file(directory, shared)
    static = regular_file(directory, "libarboresce_c.a")
    if not static.read_bytes().startswith(b"!<arch>\n"):
        raise ValueError("Invalid static archive format")
    if platform.system() == "Darwin":
        architecture = {"aarch64": "arm64", "x86_64": "x86_64"}[
            host_target().split("-")[0]
        ]
        for artifact in (library, static):
            if command_output(["lipo", "-archs", str(artifact)]).split() != [
                architecture
            ]:
                raise ValueError("Native library architecture differs from host")
        exported = command_output(["nm", "-gU", str(library)])
        symbols = sorted(
            line.split()[-1].removeprefix("_")
            for line in exported.splitlines()
            if line.strip()
        )
        if command_output(["otool", "-D", str(library)]).splitlines()[1:] != [
            "@rpath/libarboresce_c.1.dylib"
        ]:
            raise ValueError("C shared library install name differs")
        metadata = command_output(["otool", "-l", str(library)])
        if "LC_RPATH" in metadata:
            raise ValueError("Build RPATH in native library")
    else:
        exported = command_output(["nm", "-D", "--defined-only", str(library)])
        symbols = sorted(
            line.split()[-1] for line in exported.splitlines() if line.strip()
        )
        metadata = command_output(["readelf", "-d", str(library)])
        if (
            "[libarboresce_c.so.1]" not in metadata
            or "RPATH" in metadata
            or "RUNPATH" in metadata
        ):
            raise ValueError("C shared library SONAME/RPATH differs")
        architecture = {
            "aarch64": "AArch64",
            "x86_64": "Advanced Micro Devices X86-64",
        }[host_target().split("-")[0]]
        for artifact in (library, static):
            headers = command_output(["readelf", "-h", str(artifact)])
            machines = re.findall(r"Machine:\s*(.+)", headers)
            if not machines or any(
                machine.strip() != architecture for machine in machines
            ):
                raise ValueError("Native library architecture differs from host")
    if symbols != SYMBOLS:
        raise ValueError("C export inventory differs from ABI baseline")
    native = ctypes.CDLL(str(library))
    native.arboresce_v1_abi_version.restype = ctypes.c_uint32
    if native.arboresce_v1_abi_version() != 65536:
        raise ValueError("C runtime ABI version differs")


def record_build(sdk=SDK):
    sdk = Path(sdk).resolve()
    stage = sdk / "build/native/stage"
    verify_native_artifacts(stage)
    shared, _ = library_names()
    record = identity(sdk) | {
        "tools": tool_identity(sdk),
        "artifacts": {
            name: digest(regular_file(stage, name))
            for name in ("libarboresce_c.a", shared)
        },
        "native_static_libraries": regular_file(stage, "native-static-libs.txt")
        .read_text()
        .strip(),
    }
    if not record["native_static_libraries"]:
        raise ValueError("Missing native static dependency evidence")
    (sdk / "build/native/build-receipt.json").write_bytes(canonical(record))
    return record


def validate_build(sdk):
    record = json.loads(
        regular_file(sdk, "build/native/build-receipt.json").read_text()
    )
    if any(
        record.get(key) != value for key, value in identity(sdk).items()
    ) or record.get("tools") != tool_identity(sdk):
        raise ValueError("Stale native build identity; rebuild C/C++ packages")
    shared, _ = library_names()
    artifacts = {
        name: digest(regular_file(sdk / "build/native/stage", name))
        for name in ("libarboresce_c.a", shared)
    }
    if record.get("artifacts") != artifacts:
        raise ValueError("Corrupt native build artifacts")
    return record


def package_payload(sdk, kind):
    sdk = Path(sdk).resolve()
    record = validate_build(sdk)
    prefix = sdk / "build/native/install"
    shared, alias = library_names()
    known = installed_files("c") | installed_files("cpp")
    directories = {
        parent.as_posix()
        for name in known
        for parent in PurePosixPath(name).parents
        if parent != PurePosixPath(".")
    }
    for path in prefix.rglob("*"):
        name = path.relative_to(prefix).as_posix()
        if path.is_dir() and not path.is_symlink():
            if name not in directories:
                raise ValueError(f"Unexpected native package directory: {name}")
        elif name not in known:
            raise ValueError(f"Unexpected native package file: {name}")
    aliases = {f"lib/{alias}": shared}
    files = {
        name: regular_file(prefix, name, aliases).read_bytes()
        for name in sorted(installed_files(kind))
    }
    if kind == "c":
        for name, expected in record["artifacts"].items():
            if hashlib.sha256(files[f"lib/{name}"]).hexdigest() != expected:
                raise ValueError("Installed C library differs from build receipt")
        if files[f"lib/{alias}"] != files[f"lib/{shared}"]:
            raise ValueError("Installed C library alias differs")
    for name, content in documentation(sdk, kind).items():
        if files[name] != content:
            raise ValueError("Installed native documentation differs from source")
    for name, content in files.items():
        if name.endswith((".h", ".hpp")):
            if content != regular_file(sdk / "bindings" / kind, name).read_bytes():
                raise ValueError("Installed native header differs from source")
        if name.endswith((".cmake", ".pc")):
            text = content.decode()
            if (
                str(sdk) in text
                or str(prefix) in text
                or re.search(r'(?:["\'=; ]|^)/(?:[A-Za-z0-9_])', text)
            ):
                raise ValueError("Absolute build path in installed native metadata")
    files[f"share/arboresce-{kind}/abi_v1.json"] = regular_file(
        sdk, "bindings/c/tests/abi_v1.json"
    ).read_bytes()
    manifest = record | {
        "package": kind,
        "inventory": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }
    if kind == "cpp":
        c_files = package_payload(sdk, "c")
        manifest["dependency"] = {
            "package": "c",
            "version": record["version"],
            "target": record["target"],
            "abi_version": record["abi"]["abi_version"],
            "manifest_sha256": hashlib.sha256(c_files[manifest_path("c")]).hexdigest(),
        }
    files[manifest_path(kind)] = canonical(manifest)
    return files


def package_path(sdk, kind, root=None):
    version = tomllib.loads((sdk / "Cargo.toml").read_text())["workspace"]["package"][
        "version"
    ]
    return (
        Path(root or sdk / "build/dist")
        / kind
        / f"arboresce-{kind}-{version}-{host_target()}.zip"
    )


def package_native(sdk, destination, kind):
    files = package_payload(Path(sdk), kind)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        output = Path(temporary) / "native.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, content)
        output.replace(destination)
    return destination


def validate_archive(sdk, archive_path, kind):
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        for entry in entries:
            safe_name(entry.filename)
            if stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG:
                raise ValueError("Non-regular native ZIP entry")
        if len(set(names)) != len(names) or set(names) != archive_files(kind):
            raise ValueError("Native archive inventory differs")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files[manifest_path(kind)])
    if manifest.get("package") != kind or any(
        manifest.get(key) != value for key, value in identity(Path(sdk)).items()
    ):
        raise ValueError("Native archive identity differs")
    inventory = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
        if name != manifest_path(kind)
    }
    if manifest.get("inventory") != inventory:
        raise ValueError("Corrupt native archive content")
    if (
        files[f"share/arboresce-{kind}/abi_v1.json"]
        != (Path(sdk) / "bindings/c/tests/abi_v1.json").read_bytes()
    ):
        raise ValueError("Native archive ABI baseline differs")
    if (
        not manifest.get("tools", {})
        .get("rust", "")
        .startswith(f"rustc {manifest['compiler_pin']} ")
    ):
        raise ValueError("Native archive compiler identity differs")
    if (
        f"host: {manifest['target']}" not in manifest["tools"]["rust"].splitlines()
        or manifest["tools"].get("generator") != "cbindgen 0.29.4"
    ):
        raise ValueError("Native archive host/generator identity differs")
    if kind == "c":
        shared, alias = library_names()
        if manifest.get("artifacts") != {
            name: inventory[f"lib/{name}"] for name in ("libarboresce_c.a", shared)
        }:
            raise ValueError("Native archive build digests differ")
        if (
            inventory[f"lib/{alias}"] != inventory[f"lib/{shared}"]
            or inventory["include/arboresce/arboresce.h"]
            != manifest["generated_header_sha256"]
        ):
            raise ValueError("Native archive alias/header digest differs")
    for name, content in documentation(Path(sdk), kind).items():
        if files[name] != content:
            raise ValueError("Native archive documentation differs")
    for name, content in files.items():
        if (
            name.endswith((".h", ".hpp"))
            and content
            != regular_file(Path(sdk) / "bindings" / kind, name).read_bytes()
        ):
            raise ValueError("Native archive header differs")
        if name.endswith((".cmake", ".pc")) and re.search(
            r'(?:["\'=; ]|^)/(?:[A-Za-z0-9_])', content.decode()
        ):
            raise ValueError("Absolute path in native archive metadata")
    return manifest, files


def extract_native(sdk, archive_path, kind, destination):
    manifest, files = validate_archive(sdk, archive_path, kind)
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("Symlinked native extraction root")
    destination = destination.resolve()
    if kind == "cpp":
        dependency = manifest.get("dependency", {})
        c_manifest = regular_file(destination, manifest_path("c"))
        expected = {
            "package": "c",
            "version": manifest["version"],
            "target": manifest["target"],
            "abi_version": 65536,
            "manifest_sha256": digest(c_manifest),
        }
        if dependency != expected:
            raise ValueError("C++ package C dependency differs")
    for name in files:
        path = destination / name
        if (
            path.exists()
            or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)
        ):
            raise ValueError(
                "Native extraction would overwrite an existing or symlinked path"
            )
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return manifest


def qualify_packages(sdk, c_archive, cpp_archive=None):
    sdk = Path(sdk).resolve()
    spec = importlib.util.spec_from_file_location(
        "native_package_consumers", sdk / "tests/platforms/test_c_cpp.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="arboresce-native-packages-") as temporary:
        prefix = Path(temporary) / "prefix"
        extract_native(sdk, c_archive, "c", prefix)
        verify_native_artifacts(prefix / "lib")
        suites = [module.CConsumers]
        if cpp_archive is not None:
            extract_native(sdk, cpp_archive, "cpp", prefix)
            suites.append(module.CppConsumers)
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for base in suites:
            fixture = type(
                "Packaged" + base.__name__,
                (base,),
                {"package": prefix, "fixtures": sdk / "bindings"},
            )
            suite.addTests(loader.loadTestsFromTestCase(fixture))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful() or result.skipped or not result.testsRun:
            raise AssertionError("Installed native package qualification failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "record-build",
            "package-c",
            "package-cpp",
            "test-c-package",
            "test-cpp-package",
        ),
    )
    command = parser.parse_args().command
    if command == "record-build":
        record_build()
    elif command in ("package-c", "package-cpp"):
        kind = command.removeprefix("package-")
        print(package_native(SDK, package_path(SDK, kind), kind))
    else:
        qualify_packages(
            SDK,
            package_path(SDK, "c"),
            package_path(SDK, "cpp") if command == "test-cpp-package" else None,
        )


if __name__ == "__main__":
    main()
