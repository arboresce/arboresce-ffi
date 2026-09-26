import contextlib
import json
import platform
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from runtime_evidence import record
from swift_package import swift_package_paths

SDK = Path(__file__).resolve().parents[2]


def ios_version(value):
    parts = tuple(int(part) for part in value.split("."))
    return (parts + (0, 0, 0))[:3]


def select_ios_destination(runtimes, device_types, machine):
    architecture = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "x86_64",
        "AMD64": "x86_64",
    }.get(machine)
    if architecture is None:
        raise ValueError(f"Unsupported iOS simulator host architecture: {machine}")
    candidates = []
    for runtime in runtimes:
        if not runtime.get("isAvailable") or not runtime.get(
            "identifier", ""
        ).startswith("com.apple.CoreSimulator.SimRuntime.iOS-"):
            continue
        if architecture not in runtime.get("supportedArchitectures", [architecture]):
            continue
        version = ios_version(runtime["version"])
        supported = {
            device["identifier"] for device in runtime.get("supportedDeviceTypes", [])
        }
        for device in device_types:
            if device.get("productFamily") not in ("iPhone", "iPad"):
                continue
            if supported and device["identifier"] not in supported:
                continue
            if (
                not ios_version(device.get("minRuntimeVersionString", "0"))
                <= version
                <= ios_version(device.get("maxRuntimeVersionString", "65535.255.255"))
            ):
                continue
            candidates.append(
                (
                    version,
                    device.get("productFamily") == "iPhone",
                    device["identifier"],
                    runtime["identifier"],
                )
            )
    if not candidates:
        raise ValueError(
            f"Install an available iOS simulator runtime and compatible iPhone/iPad device type for {architecture}"
        )
    _, _, device, runtime = max(candidates)
    return runtime, device, architecture


@contextlib.contextmanager
def owned_ios_simulator(checked, runtime, device_type):
    device = checked(
        [
            "xcrun",
            "simctl",
            "create",
            "Arboresce-" + uuid.uuid4().hex,
            device_type,
            runtime,
        ]
    )
    try:
        yield device
    finally:
        try:
            subprocess.run(
                ["xcrun", "simctl", "shutdown", device], capture_output=True, timeout=60
            )
        finally:
            checked(["xcrun", "simctl", "delete", device])


class IOSConsumer(unittest.TestCase):
    package = SDK
    fixtures = SDK / "tests/platforms/fixtures"

    def run_checked(self, command, cwd=None):
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=240
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def test_packaged_simulator_consumer(self):
        runtimes = json.loads(
            self.run_checked(["xcrun", "simctl", "list", "runtimes", "-j"])
        )["runtimes"]
        device_types = json.loads(
            self.run_checked(["xcrun", "simctl", "list", "devicetypes", "-j"])
        )["devicetypes"]
        runtime, device_type, architecture = select_ios_destination(
            runtimes, device_types, platform.machine()
        )
        with tempfile.TemporaryDirectory(prefix="arb-ios-") as temporary:
            root = Path(temporary)
            sources, xcframework = swift_package_paths(self.package)
            framework = xcframework / "ios-arm64_x86_64-simulator"
            sdk = self.run_checked(
                ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"]
            )
            base = [
                "xcrun",
                "swiftc",
                "-target",
                f"{architecture}-apple-ios13.0-simulator",
                "-sdk",
                sdk,
                "-I",
                str(framework / "Headers"),
                "-I",
                str(root),
                "-L",
                str(root),
            ]
            self.run_checked(
                base
                + [
                    "-parse-as-library",
                    "-emit-library",
                    "-static",
                    "-emit-module",
                    "-module-name",
                    "ArboresceBindings",
                    str(sources / "ArboresceBindings/ArboresceBindings.swift"),
                    "-o",
                    str(root / "libArboresceBindings.a"),
                ],
                root,
            )
            self.run_checked(
                base
                + [
                    "-parse-as-library",
                    "-emit-library",
                    "-static",
                    "-emit-module",
                    "-module-name",
                    "Arboresce",
                    str(sources / "Arboresce/Arboresce.swift"),
                    "-o",
                    str(root / "libArboresce.a"),
                ],
                root,
            )
            shutil.copyfile(self.fixtures / "swift/main.swift", root / "main.swift")
            self.run_checked(
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
            with owned_ios_simulator(self.run_checked, runtime, device_type) as device:
                self.run_checked(["xcrun", "simctl", "boot", device])
                self.run_checked(["xcrun", "simctl", "bootstatus", device, "-b"])
                self.assertEqual(
                    self.run_checked(
                        ["xcrun", "simctl", "spawn", device, str(root / "Consumer")]
                    ),
                    "Arboresce",
                )
                record(
                    "swift",
                    "ios-sim-arm64" if architecture == "arm64" else "ios-sim-x64",
                    "simulator",
                    {"runtime": runtime, "device_type": device_type},
                    cpu=architecture,
                )
                print(
                    "iOS runtime: "
                    + json.dumps(
                        {
                            "runtime": runtime,
                            "device_type": device_type,
                            "architecture": architecture,
                            "execution": "simulator",
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
