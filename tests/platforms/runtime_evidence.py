import json
import os
import platform
import subprocess
from pathlib import Path

MODES = {
    "native",
    "rosetta",
    "container-native",
    "container-emulated",
    "simulator",
    "emulator",
    "link",
    "browser",
}


def architecture(value=None):
    value = value or platform.machine()
    return {"aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(
        value.lower(), value.lower()
    )


def record(language, target, execution, runtime, *, cpu=None):
    if execution not in MODES or not runtime:
        raise ValueError("Invalid runtime execution evidence")
    entry = {
        "schema": 1,
        "language": language,
        "target": target,
        "execution": execution,
        "architecture": architecture(cpu),
        "host": platform.platform(),
        "runtime": runtime,
        "minimum_runtime": False,
        "suite": os.environ.get("ARBORESCE_TEST_SUITE", "public"),
    }
    destination = os.environ.get("ARBORESCE_TEST_EVIDENCE")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def container_runtime(image, cpu):
    engine = subprocess.check_output(
        ["docker", "info", "--format", "{{.Architecture}}"], text=True
    ).strip()
    container = subprocess.check_output(
        [
            "docker",
            "create",
            "--network=none",
            "--platform",
            f"linux/{cpu}",
            "--entrypoint",
            "sh",
            image,
            "-ec",
            "uname -m; uname -r; cat /etc/os-release; getconf GNU_LIBC_VERSION",
        ],
        text=True,
    ).strip()
    try:
        identity = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Image}}", container], text=True
        ).strip()
        system = subprocess.check_output(
            ["docker", "start", "--attach", container], text=True
        ).strip()
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container], check=True, capture_output=True
        )
    mode = (
        "container-native"
        if architecture(engine) == architecture(cpu)
        else "container-emulated"
    )
    return mode, {
        "image": image,
        "image_id": identity,
        "system": system,
        "docker_architecture": engine,
    }
