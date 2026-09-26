import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from runtime_evidence import architecture, container_runtime, record

SDK = Path(__file__).resolve().parents[2]


class GoPlatforms(unittest.TestCase):
    module = SDK / "bindings/go"

    def test_platform_consumers_and_failures(self):
        with tempfile.TemporaryDirectory(prefix="arboresce-go-matrix-") as temporary:
            root = Path(temporary)
            module = root / "arboresce-go-0.0.0"
            shutil.copytree(self.module, module)
            consumer = root / "consumer"
            shutil.copytree(SDK / "tests/platforms/fixtures/go", consumer)
            matrix = [
                ("darwin", "arm64", "clang -arch arm64"),
                ("darwin", "amd64", "clang -arch x86_64"),
                ("linux", "arm64", "zig cc -target aarch64-linux-gnu.2.17"),
                ("linux", "amd64", "zig cc -target x86_64-linux-gnu.2.17"),
            ]
            for system, arch, compiler in matrix:
                with self.subTest(platform=f"{system}_{arch}"):
                    env = dict(
                        os.environ,
                        GOOS=system,
                        GOARCH=arch,
                        CGO_ENABLED="1",
                        CC=compiler,
                        GOWORK="off",
                    )
                    binary = root / f"consumer-{system}-{arch}"
                    result = subprocess.run(
                        ["go", "build", "-o", str(binary), "."],
                        cwd=consumer,
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if system == "darwin":
                        command = [
                            "/usr/bin/arch",
                            "-arm64" if arch == "arm64" else "-x86_64",
                            str(binary),
                        ]
                    else:
                        command = [
                            "docker",
                            "run",
                            "--rm",
                            "--network=none",
                            "--platform",
                            f"linux/{arch}",
                            "--mount",
                            f"type=bind,src={root},dst=/consumer,readonly",
                            "--entrypoint",
                            f"/consumer/{binary.name}",
                            "node:22.22.3-bookworm-slim",
                        ]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "Arboresce\n")
                    target = f"{'macos' if system == 'darwin' else 'linux'}-{architecture(arch)}"
                    if system == "darwin":
                        mode = (
                            "native"
                            if architecture(arch) == architecture()
                            else "rosetta"
                        )
                        runtime = {"os": platform.platform()}
                    else:
                        mode, runtime = container_runtime(
                            "node:22.22.3-bookworm-slim", arch
                        )
                    runtime["go"] = subprocess.check_output(
                        ["go", "version"], text=True
                    ).strip()
                    record("go", target, mode, runtime, cpu=arch)
            env = dict(
                os.environ, GOOS="darwin", GOARCH="arm64", CGO_ENABLED="0", GOWORK="off"
            )
            result = subprocess.run(
                ["go", "build", "."],
                cwd=consumer,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("build constraints", result.stderr)
            (module / "internal/native/lib/darwin_arm64/libarboresce_ffi.a").unlink()
            env.update(CGO_ENABLED="1", CC="clang -arch arm64")
            result = subprocess.run(
                ["go", "build", "-o", str(root / "missing"), "."],
                cwd=consumer,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("libarboresce_ffi.a", result.stderr)
            env.update(GOOS="windows", GOARCH="amd64")
            result = subprocess.run(
                ["bash", "scripts/make.sh", "doctor-go"],
                cwd=SDK,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported", result.stderr.lower())
