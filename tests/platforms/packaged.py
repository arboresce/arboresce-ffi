import argparse
import importlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime_evidence import architecture, record
from test_android import AndroidConsumer
from test_go_platforms import GoPlatforms
from test_ios import IOSConsumer
from test_linux_packages import LinuxPackages
from test_maven_resolution import MavenResolution
from test_swift_platforms import SwiftPlatforms

SDK = Path(__file__).resolve().parents[2]


def run_suite(base, attributes):
    fixture = type("Packaged" + base.__name__, (base,), attributes)
    suite = unittest.TestLoader().loadTestsFromTestCase(fixture)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or not result.testsRun:
        raise AssertionError("Packaged platform checks failed")


def consumer_tools():
    original = sys.path[:]
    try:
        sys.path.insert(0, str(SDK / "tests/consumers"))
        return tuple(
            importlib.import_module(name)
            for name in ("native_packages", "package_tools", "swift_packages")
        )
    finally:
        sys.path[:] = original


def host_runtime(cpu):
    system = {"Darwin": "macos", "Linux": "linux"}.get(platform.system())
    cpu = architecture(cpu)
    if system is None or cpu not in {"arm64", "x64"}:
        raise ValueError("Unsupported packaged host")
    mode = "native"
    if system == "macos" and cpu == "x64":
        arm = subprocess.check_output(
            ["sysctl", "-n", "hw.optional.arm64"], text=True
        ).strip()
        if arm == "1":
            mode = "rosetta"
    return system + "-" + cpu, mode, cpu


def host_record(language, cpu, runtime):
    target, mode, cpu = host_runtime(cpu)
    record(language, target, mode, runtime, cpu=cpu)


def python_consumer(root, artifacts, release):
    wheel = artifacts / "python"
    if not any(wheel.glob("*.whl")):
        raise FileNotFoundError("Prepared Python wheels are missing")
    environment = root / "python"
    subprocess.run(
        ["uv", "venv", "--python", "3.14.7", "--no-python-downloads", str(environment)],
        check=True,
    )
    python = environment / "bin/python"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-cache",
            "--no-deps",
            "--no-index",
            "--find-links",
            str(wheel),
            "arboresce==" + release,
        ],
        check=True,
    )
    identity = root / "python-runtime.json"
    subprocess.run(
        [
            str(python),
            "-I",
            str(SDK / "tests/platforms/python_runtime.py"),
            str(SDK / "bindings/python/tests"),
            "--identity",
            str(identity),
        ],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(SDK / "tests/consumers/python_types.py"), str(python)],
        check=True,
    )
    runtime = json.loads(identity.read_text())
    host_record("python", runtime.pop("architecture"), runtime)


def check(language, artifacts, go_module_zip=None):
    if go_module_zip is not None and language != "go":
        raise ValueError("A prepared Go module ZIP requires the Go consumer")
    native, packages, swift = consumer_tools()
    artifacts = Path(artifacts).resolve(strict=True)
    release = packages.version(SDK)
    with tempfile.TemporaryDirectory(
        prefix="arboresce-packaged-platform-"
    ) as temporary:
        root = Path(temporary)
        if language == "python":
            python_consumer(root, artifacts, release)
        elif language == "typescript":
            if not (artifacts / f"npm/arboresce-{release}.tgz").is_file():
                raise FileNotFoundError("Prepared npm package is missing")
            packages.test_typescript_consumer(browser=True, artifacts=artifacts / "npm")
            identity = json.loads(
                subprocess.check_output(
                    [
                        "node",
                        "-p",
                        "JSON.stringify({node:process.version,architecture:process.arch,os:process.platform})",
                    ],
                    text=True,
                )
            )
            host_record("typescript", identity.pop("architecture"), identity)
        elif language == "kotlin":
            bundle = artifacts / f"maven/arboresce-{release}-central-bundle.zip"
            repository = bundle if bundle.is_file() else artifacts / "maven"
            if repository.is_dir():
                packages.validate_maven(artifacts=repository)
            if not repository.exists():
                raise FileNotFoundError("Prepared Maven package is missing")
            packages.test_kotlin_consumer(artifacts=repository)
            java = subprocess.run(
                ["java", "-XshowSettings:properties", "-version"],
                check=True,
                capture_output=True,
                text=True,
            )
            details = (java.stdout + java.stderr).strip()
            matches = re.findall(r"(?m)^\s*os.arch\s*=\s*(\S+)\s*$", details)
            if len(matches) != 1:
                raise ValueError("Java runtime architecture is unavailable")
            host_record(
                "kotlin", matches[0], {"java": details, "os": platform.platform()}
            )
        elif language == "linux":
            run_suite(LinuxPackages, {"artifacts": artifacts})
        elif language == "go":
            packages.extract_zip(artifacts / f"go/arboresce-go-{release}.zip", root)
            run_suite(
                GoPlatforms,
                {
                    "module": root / f"arboresce-go-{release}",
                    "module_zip": go_module_zip,
                },
            )
        elif language in {"swift", "ios"}:
            artifact = artifacts / f"swift/arboresce-swift-{release}.zip"
            package = swift.extract_package(artifact, root / "package", release)
            if language == "swift":
                swift.test_swift_consumer(artifact=artifact)
                record(
                    "swift",
                    "macos-" + architecture(),
                    "native",
                    {
                        "os": platform.platform(),
                        "swift": subprocess.check_output(
                            ["/usr/bin/swift", "--version"], text=True
                        ).strip(),
                    },
                )
            run_suite(
                SwiftPlatforms if language == "swift" else IOSConsumer,
                {"package": package},
            )
        elif language == "android":
            repository = artifacts / "maven"
            bundle = repository / f"arboresce-{release}-central-bundle.zip"
            if bundle.is_file():
                repository = root / "maven"
                packages.extract_zip(bundle, repository)
            packages.validate_maven(artifacts=repository)
            packages.validate_maven(android=True, artifacts=repository)
            run_suite(MavenResolution, {})
            run_suite(AndroidConsumer, {"repository_directory": repository})
        elif language in {"c", "cpp"}:
            target = native.host_target()
            c_archive = artifacts / f"c/arboresce-c-{release}-{target}.zip"
            cpp_archive = artifacts / f"cpp/arboresce-cpp-{release}-{target}.zip"
            native.qualify_packages(
                SDK, c_archive, cpp_archive if language == "cpp" else None
            )
            for name in ("c", "cpp") if language == "cpp" else ("c",):
                record(
                    name,
                    "macos-" + architecture()
                    if sys.platform == "darwin"
                    else "linux-" + architecture(),
                    "native",
                    {"os": platform.platform()},
                )
        else:
            raise ValueError("Unsupported packaged platform")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "language",
        choices=(
            "python",
            "typescript",
            "kotlin",
            "linux",
            "go",
            "swift",
            "ios",
            "android",
            "c",
            "cpp",
        ),
    )
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--go-module-zip", type=Path)
    arguments = parser.parse_args()
    check(arguments.language, arguments.artifacts, arguments.go_module_zip)


if __name__ == "__main__":
    main()
