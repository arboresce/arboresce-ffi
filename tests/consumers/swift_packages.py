import argparse
import os
import plistlib
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

from package_tools import version, write_zip

SDK = Path(__file__).resolve().parents[2]
ROOT_FILES = {"Package.swift", "README.md", "LICENSE-MIT", "LICENSE-APACHE"}
ROOT_DIRECTORIES = {"Sources", "Tests", "Arboresce.xcframework"}


def regular_files(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"Missing or symlinked Swift input directory: {directory}")
    files = {}
    for path in sorted(directory.rglob("*")):
        if any(
            part.startswith(".") or part in {"build", "target", "__pycache__"}
            for part in path.relative_to(directory).parts
        ):
            raise ValueError(f"Local state in Swift package input: {path}")
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError(f"Unsupported Swift package input: {path}")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path
    if not files:
        raise ValueError(f"Empty Swift input directory: {directory}")
    return files


def staged_files(sdk):
    staged = sdk / "build/swift-dev"
    allowed = ROOT_FILES | ROOT_DIRECTORIES
    if not staged.is_dir() or staged.is_symlink():
        raise ValueError("Missing staged Swift package; run make build-swift")
    if {path.name for path in staged.iterdir()} - allowed - {".build"}:
        raise ValueError("Unexpected staged Swift package inventory")
    files = {}
    for name in ROOT_FILES:
        path = staged / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or symlinked Swift package file: {name}")
        files[name] = path
    if (
        files["Package.swift"].read_bytes()
        != (sdk / "bindings/swift/dev/Package.swift").read_bytes()
    ):
        raise ValueError(
            "Staged Swift manifest differs from the local package manifest"
        )
    for name in ROOT_DIRECTORIES:
        actual = regular_files(staged / name)
        source = (
            sdk
            / ("build/swift" if name == "Arboresce.xcframework" else "bindings/swift")
            / name
        )
        canonical = regular_files(source)
        if actual.keys() != canonical.keys() or any(
            actual[key].read_bytes() != canonical[key].read_bytes() for key in actual
        ):
            raise ValueError(f"Stale staged Swift {name}")
        files.update({f"{name}/{key}": path for key, path in actual.items()})
    if "Arboresce.xcframework/Info.plist" not in files:
        raise ValueError("Swift package has no XCFramework manifest")
    return files


def normalize_framework(sdk=SDK):
    framework = Path(sdk) / "build/swift/Arboresce.xcframework"
    if framework.is_symlink():
        raise ValueError("Unsupported Swift framework symlink")
    manifest = regular_files(framework)["Info.plist"]
    value = plistlib.loads(manifest.read_bytes())
    libraries = value["AvailableLibraries"]
    identities = [library["LibraryIdentifier"] for library in libraries]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate framework library")
    for library in libraries:
        library["SupportedArchitectures"] = sorted(library["SupportedArchitectures"])
    libraries.sort(key=lambda library: library["LibraryIdentifier"])
    manifest.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=True))


def package_swift(sdk=SDK):
    sdk = Path(sdk)
    release = version(sdk)
    files = staged_files(sdk)
    destination = sdk / "build/dist/swift"
    package = destination / f"arboresce-swift-{release}.zip"
    write_zip(files, package, f"arboresce-swift-{release}")
    prefix = "Arboresce.xcframework/"
    framework = {
        name.removeprefix(prefix): path
        for name, path in files.items()
        if name.startswith(prefix)
    }
    write_zip(
        framework, destination / "Arboresce.xcframework.zip", "Arboresce.xcframework"
    )
    print(f"Prepared Swift package and XCFramework ZIPs: {destination}")
    return package


def extract_package(artifact, destination, release):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Swift extraction destination must not exist")
    prefix = f"arboresce-swift-{release}"
    with zipfile.ZipFile(artifact) as archive:
        files = {}
        for entry in archive.infolist():
            path = Path(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 2
                or path.parts[0] != prefix
                or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG
            ):
                raise ValueError("Unsafe Swift package ZIP entry")
            name = Path(*path.parts[1:]).as_posix()
            if name in files:
                raise ValueError("Duplicate Swift package ZIP entry")
            if path.parts[1] not in ROOT_FILES | ROOT_DIRECTORIES or (
                path.parts[1] in ROOT_FILES and len(path.parts) != 2
            ):
                raise ValueError("Unexpected Swift package ZIP entry")
            if any(
                part in {".build", "build", "target", ".git", "__pycache__"}
                for part in path.parts[1:]
            ):
                raise ValueError("Build or repository state in Swift package")
            files[name] = archive.read(entry)
        required = ROOT_FILES | {
            "Arboresce.xcframework/Info.plist",
            "Sources/Arboresce/Arboresce.swift",
            "Sources/ArboresceBindings/ArboresceBindings.swift",
            "Tests/ArboresceTests/ArboresceTests.swift",
            "Tests/Fixtures/PrintName/main.swift",
        }
        if not required.issubset(files):
            raise ValueError("Incomplete Swift package ZIP inventory")
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return destination


def test_swift_consumer(sdk=SDK, artifact=None):
    sdk = Path(sdk)
    release = version(sdk)
    artifact = (
        Path(artifact)
        if artifact
        else sdk / f"build/dist/swift/arboresce-swift-{release}.zip"
    )
    with tempfile.TemporaryDirectory(prefix="arboresce swift consumer ") as temporary:
        root = Path(temporary)
        package = extract_package(artifact, root / "package", release)
        consumer = root / "consumer"
        shutil.copytree(sdk / "tests/consumers/swift", consumer)
        shutil.copytree(
            package / "Tests/ArboresceTests", consumer / "Tests/ArboresceTests"
        )
        shutil.copytree(
            package / "Tests/Fixtures/PrintName", consumer / "Sources/PrintName"
        )
        env = dict(
            os.environ,
            PATH="/usr/bin:/bin:/usr/sbin:/sbin",
            CARGO_HOME=str(root / "no-cargo"),
            RUSTUP_HOME=str(root / "no-rustup"),
        )
        for key in (
            "CPATH",
            "C_INCLUDE_PATH",
            "CPLUS_INCLUDE_PATH",
            "LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "DYLD_FALLBACK_LIBRARY_PATH",
            "LD_LIBRARY_PATH",
        ):
            env.pop(key, None)
        subprocess.run(
            [
                "/usr/bin/swift",
                "test",
                "--package-path",
                str(consumer),
                "--scratch-path",
                str(root / "build"),
            ],
            cwd=root,
            env=env,
            check=True,
        )
        print("PASS: Extracted Swift package consumer with Rust absent from PATH")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("normalize", "package", "test"))
    parser.add_argument("--artifact", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "normalize":
        normalize_framework()
    elif arguments.command == "package":
        package_swift()
    else:
        test_swift_consumer(artifact=arguments.artifact)


if __name__ == "__main__":
    main()
