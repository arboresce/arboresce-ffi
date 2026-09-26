import contextlib
import fcntl
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from android_elf import check_apk_native
from runtime_evidence import record

SDK = Path(__file__).resolve().parents[2]


def android_properties(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")) and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def select_android_image(android, machine):
    architecture = {
        "arm64": "arm64-v8a",
        "aarch64": "arm64-v8a",
        "x86_64": "x86_64",
        "AMD64": "x86_64",
    }.get(machine)
    if architecture is None:
        raise ValueError(f"Unsupported Android emulator host architecture: {machine}")
    candidates = []
    for properties in (android / "system-images").glob("*/*/*/source.properties"):
        values = android_properties(properties)
        api = values.get("AndroidVersion.ApiLevel", "")
        tag = values.get("SystemImage.TagId", "")
        if (
            values.get("SystemImage.Abi") != architecture
            or not api.isdecimal()
            or int(api) < 35
        ):
            continue
        if "ps16k" not in tag.lower() and not re.search(
            r"16\s*(?:kb|kib)", values.get("SystemImage.TagDisplay", ""), re.I
        ):
            continue
        package = ";".join(properties.parent.relative_to(android).parts)
        candidates.append((int(api), package))
    if not candidates:
        raise ValueError(
            f"Install a Google APIs 16 KB page-size system image for {architecture} (API 35 or newer) in {android}; ordinary Google APIs images do not qualify"
        )
    return max(candidates)[1]


def require_page_size(output):
    try:
        value = int(output.strip())
    except ValueError as error:
        raise ValueError(f"Invalid Android PAGE_SIZE: {output.strip()!r}") from error
    if value != 16384:
        raise ValueError(
            f"Android runtime PAGE_SIZE is {value}; qualification requires 16384"
        )
    return value


@contextlib.contextmanager
def reserve_emulator_port(directory=None, ports=range(5554, 5683, 2)):
    directory = (
        Path(directory)
        if directory is not None
        else Path(tempfile.gettempdir()) / f"arboresce-emulator-ports-{os.getuid()}"
    )
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for port in ports:
        with (directory / str(port)).open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            with contextlib.ExitStack() as sockets:
                held = []
                try:
                    for number in (port, port + 1):
                        connection = sockets.enter_context(socket.socket())
                        connection.bind(("127.0.0.1", number))
                        held.append(connection)
                except OSError:
                    continue
                yield port, lambda: [connection.close() for connection in held]
                return
    raise ValueError("No free Android emulator console/ADB port pair is available")


class AndroidConsumer(unittest.TestCase):
    android = Path(
        os.environ.get(
            "ANDROID_HOME",
            str(
                Path.home()
                / (
                    "Library/Android/sdk"
                    if platform.system() == "Darwin"
                    else "Android/Sdk"
                )
            ),
        )
    )
    repository_archive = None
    sdk = SDK

    def checked(self, command, **kwargs):
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=300, **kwargs
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_packaged_android_consumer(self):
        android = self.android
        image = select_android_image(android, platform.machine())
        for name in (
            "build-tools/36.0.0/zipalign",
            "cmdline-tools/latest/bin/avdmanager",
            "platform-tools/adb",
            "emulator/emulator",
        ):
            self.assertTrue(
                (android / name).is_file(),
                f"Missing Android prerequisite: {android / name}",
            )
        with contextlib.ExitStack() as cleanup:
            temporary = cleanup.enter_context(
                tempfile.TemporaryDirectory(prefix="arb-android-")
            )
            root = Path(temporary)
            project = root / "consumer"
            shutil.copytree(
                self.sdk / "bindings/kotlin/android-smoke",
                project,
                ignore=shutil.ignore_patterns("build", ".gradle", ".kotlin"),
            )
            if self.repository_archive is not None:
                with zipfile.ZipFile(self.repository_archive) as archive:
                    archive.extractall(project / "repository")
            env = dict(
                os.environ,
                ANDROID_HOME=str(android),
                ANDROID_SDK_ROOT=str(android),
                ANDROID_AVD_HOME=str(root / "avd"),
            )
            self.checked(
                [
                    str(self.sdk / "bindings/kotlin/gradlew"),
                    "--no-daemon",
                    "assembleDebug",
                    f"-PsdkSource={self.sdk / 'bindings/kotlin'}",
                ],
                cwd=project,
                env=env,
            )
            apk = project / "build/outputs/apk/debug/arboresce-consumer-debug.apk"
            self.checked(
                [
                    str(android / "build-tools/36.0.0/zipalign"),
                    "-c",
                    "-P",
                    "16",
                    "4",
                    str(apk),
                ]
            )
            with zipfile.ZipFile(apk) as archive:
                inventory = check_apk_native(
                    archive, ("arm64-v8a", "armeabi-v7a", "x86_64")
                )
            print(
                "Android APK native inventory: "
                + json.dumps(inventory, sort_keys=True),
                flush=True,
            )
            device = "arboresce_" + uuid.uuid4().hex
            manager = str(android / "cmdline-tools/latest/bin/avdmanager")
            self.checked(
                [
                    manager,
                    "create",
                    "avd",
                    "--name",
                    device,
                    "--path",
                    str(root / "device.avd"),
                    "--package",
                    image,
                ],
                input="no\n",
                env=env,
            )
            cleanup.callback(
                lambda: subprocess.run(
                    [manager, "delete", "avd", "--name", device],
                    env=env,
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
            )
            port, release_sockets = cleanup.enter_context(reserve_emulator_port())
            adb = [str(android / "platform-tools/adb"), "-s", f"emulator-{port}"]
            with (root / "emulator.log").open("w") as log:
                release_sockets()
                process = subprocess.Popen(
                    [
                        str(android / "emulator/emulator"),
                        "-avd",
                        device,
                        "-port",
                        str(port),
                        "-no-window",
                        "-no-audio",
                        "-no-snapshot",
                        "-gpu",
                        "swiftshader_indirect",
                        "-no-boot-anim",
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    deadline = time.monotonic() + 240
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            self.fail((root / "emulator.log").read_text())
                        result = subprocess.run(
                            adb + ["shell", "getprop", "sys.boot_completed"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0 and result.stdout.strip() == "1":
                            break
                        time.sleep(2)
                    else:
                        self.fail("Android emulator did not boot")
                    self.assertIsNone(process.poll(), "Owned Android emulator exited")
                    self.assertEqual(
                        self.checked(adb + ["emu", "avd", "name"]).splitlines()[0],
                        device,
                        "Selected Android device is not owned by this test",
                    )
                    page_size = require_page_size(
                        self.checked(adb + ["shell", "getconf", "PAGE_SIZE"])
                    )
                    api = self.checked(
                        adb + ["shell", "getprop", "ro.build.version.sdk"]
                    ).strip()
                    architecture = self.checked(
                        adb + ["shell", "getprop", "ro.product.cpu.abi"]
                    ).strip()
                    print(
                        "Android runtime: "
                        + json.dumps(
                            {
                                "image": image,
                                "api": api,
                                "abi": architecture,
                                "page_size": page_size,
                                "execution": "emulator",
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    self.checked(adb + ["install", str(apk)])
                    self.checked(adb + ["logcat", "-c"])
                    self.checked(
                        adb
                        + [
                            "shell",
                            "am",
                            "start",
                            "-W",
                            "-n",
                            "ai.arboresce.consumer/.MainActivity",
                        ]
                    )
                    for _ in range(30):
                        logs = self.checked(adb + ["logcat", "-d"])
                        if "ARBORESCE_CONSUMER_OK" in logs:
                            break
                        time.sleep(1)
                    self.assertIn("ARBORESCE_CONSUMER_OK", logs)
                    self.assertNotIn("FATAL EXCEPTION", logs)
                    record(
                        "android",
                        {"arm64-v8a": "android-arm64", "x86_64": "android-x64"}[
                            architecture
                        ],
                        "emulator",
                        {
                            "image": image,
                            "api": int(api),
                            "abi": architecture,
                            "page_size": page_size,
                        },
                        cpu="arm64" if architecture == "arm64-v8a" else "x64",
                    )
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
