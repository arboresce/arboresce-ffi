import argparse
import importlib
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime_evidence import architecture, record
from test_android import AndroidConsumer
from test_go_platforms import GoPlatforms
from test_ios import IOSConsumer
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
        if language == "go":
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
        "language", choices=("go", "swift", "ios", "android", "c", "cpp")
    )
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--go-module-zip", type=Path)
    arguments = parser.parse_args()
    check(arguments.language, arguments.artifacts, arguments.go_module_zip)


if __name__ == "__main__":
    main()
