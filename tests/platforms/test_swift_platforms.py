import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime_evidence import record
from swift_package import swift_package_paths

SDK = Path(__file__).resolve().parents[2]


class SwiftPlatforms(unittest.TestCase):
    package = SDK
    fixtures = SDK / "tests/platforms/fixtures"

    def check(self, command, cwd):
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=240
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def consumer(self, target, sdk_name, slice_name, execute=False):
        with tempfile.TemporaryDirectory(prefix="arb-swift-platform-") as temporary:
            root = Path(temporary)
            sources, xcframework = swift_package_paths(self.package)
            framework = xcframework / slice_name
            sdk = self.check(["xcrun", "--sdk", sdk_name, "--show-sdk-path"], root)
            base = [
                "xcrun",
                "swiftc",
                "-target",
                target,
                "-sdk",
                sdk,
                "-I",
                str(framework / "Headers"),
                "-I",
                str(root),
                "-L",
                str(root),
            ]
            for module, file in [
                ("ArboresceBindings", "ArboresceBindings.swift"),
                ("Arboresce", "Arboresce.swift"),
            ]:
                self.check(
                    base
                    + [
                        "-parse-as-library",
                        "-emit-library",
                        "-static",
                        "-emit-module",
                        "-module-name",
                        module,
                        str(sources / module / file),
                        "-o",
                        str(root / f"lib{module}.a"),
                    ],
                    root,
                )
            shutil.copyfile(self.fixtures / "swift/main.swift", root / "main.swift")
            self.check(
                base
                + [
                    str(root / "main.swift"),
                    "-lArboresce",
                    "-lArboresceBindings",
                    str(framework / "libarboresce_ffi.a"),
                    "-o",
                    str(root / "Consumer"),
                ],
                root,
            )
            if execute:
                self.assertEqual(
                    self.check(
                        ["/usr/bin/arch", "-x86_64", str(root / "Consumer")], root
                    ),
                    "Arboresce",
                )
            evidence = "build/link only"
            if execute:
                evidence = (
                    "Rosetta runtime execution"
                    if platform.machine() in ("arm64", "aarch64")
                    else "native runtime execution"
                )
            print(f"Swift target: {target}; evidence: {evidence}", flush=True)
            policy_target = (
                "macos-x64"
                if "macosx" in target
                else "ios-sim-x64"
                if "simulator" in target
                else "ios-arm64"
            )
            record(
                "swift",
                policy_target,
                "link"
                if not execute
                else "rosetta"
                if platform.machine() in ("arm64", "aarch64")
                else "native",
                {
                    "target": target,
                    "sdk": sdk_name,
                    "os": platform.platform(),
                    "swift": self.check(["swift", "--version"], root),
                },
                cpu="x64" if target.startswith("x86_64") else "arm64",
            )

    def test_macos_x64_runtime(self):
        self.consumer("x86_64-apple-macosx11.0", "macosx", "macos-arm64_x86_64", True)

    def test_ios_device_link(self):
        self.consumer("arm64-apple-ios13.0", "iphoneos", "ios-arm64")

    def test_ios_x64_simulator_link(self):
        self.consumer(
            "x86_64-apple-ios13.0-simulator",
            "iphonesimulator",
            "ios-arm64_x86_64-simulator",
        )
