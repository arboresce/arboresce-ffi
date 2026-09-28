import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SDK = Path(__file__).resolve().parents[2]


class RustFlags(unittest.TestCase):
    def flags(self, root, overrides):
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"CARGO_ENCODED_RUSTFLAGS", "RUSTFLAGS"}
        }
        environment.update(
            ROOT=str(root),
            CARGO_HOME=str(root / "cargo cache"),
            CARGO_TARGET_DIR=str(root / "target outputs"),
            **overrides,
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                'set -euo pipefail; source "$1"; prepare_rust_flags; '
                'printf "%s" "$CARGO_ENCODED_RUSTFLAGS"',
                "bash",
                str(SDK / "scripts/rust.sh"),
            ],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.split("\x1f")

    def test_encoded_flags_take_precedence_and_preserve_spaces(self):
        with tempfile.TemporaryDirectory(prefix="sdk rust flags ") as temporary:
            root = Path(temporary)
            for value in ("", "--cfg=retained\x1f-Ldependency=/path with spaces"):
                with self.subTest(encoded=value):
                    flags = self.flags(
                        root,
                        {"CARGO_ENCODED_RUSTFLAGS": value, "RUSTFLAGS": "--invalid"},
                    )
                    self.assertNotIn("--invalid", flags)
                    self.assertEqual(
                        [flag for flag in flags if not flag.startswith("--remap-")],
                        value.split("\x1f") if value else [],
                    )
                    self.assertIn(
                        f"--remap-path-prefix={root}=/src/arboresce-ffi", flags
                    )

    def test_plain_flags_split_whitespace_without_expanding_globs(self):
        with tempfile.TemporaryDirectory() as temporary:
            flags = self.flags(
                Path(temporary),
                {"RUSTFLAGS": "  --cfg=retained\n-Ldependency=*\t-C\ropt-level=1 "},
            )
            self.assertEqual(
                flags[:4], ["--cfg=retained", "-Ldependency=*", "-C", "opt-level=1"]
            )

    def test_real_compiler_remaps_macro_and_debug_paths_with_spaces(self):
        rustc = subprocess.check_output(["rustup", "which", "rustc"], text=True).strip()
        with tempfile.TemporaryDirectory(prefix="sdk rust paths ") as temporary:
            root = Path(temporary).resolve()
            cargo = root / "cargo cache"
            cargo.mkdir()
            flags = self.flags(root, {})
            for directory, expected in (
                (root, "/src/arboresce-ffi/probe.rs"),
                (cargo, "/cargo/probe.rs"),
            ):
                with self.subTest(directory=directory):
                    source = directory / "probe.rs"
                    source.write_text('fn main() { println!("{}", file!()); }\n')
                    binary = root / "probe"
                    object_file = root / "probe.o"
                    subprocess.run(
                        [
                            rustc,
                            *flags,
                            "-Cdebuginfo=2",
                            "--emit=obj",
                            str(source),
                            "-o",
                            str(object_file),
                        ],
                        check=True,
                        capture_output=True,
                    )
                    self.assertFalse(str(root).encode() in object_file.read_bytes())
                    subprocess.run(
                        [
                            rustc,
                            *flags,
                            "-Cdebuginfo=0",
                            str(source),
                            "-o",
                            str(binary),
                        ],
                        check=True,
                        capture_output=True,
                    )
                    self.assertEqual(
                        subprocess.check_output([str(binary)], text=True).strip(),
                        expected,
                    )
                    self.assertFalse(str(root).encode() in binary.read_bytes())
