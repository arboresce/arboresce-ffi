import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from package_tools import digest, distribution_files, package_go, run, write_go_proxy


class ProcessCaptureTests(unittest.TestCase):
    def test_separate_capture_preserves_stdout_and_stderr(self):
        result = run(
            [
                sys.executable,
                "-c",
                "import sys; print('result'); print('diagnostic', file=sys.stderr)",
            ],
            capture=True,
            merge_stderr=False,
        )
        self.assertEqual(result.stdout, "result\n")
        self.assertEqual(result.stderr, "diagnostic\n")

    def test_failed_separate_capture_retains_both_streams(self):
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            run(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('result'); print('failure', file=sys.stderr); sys.exit(7)",
                ],
                capture=True,
                merge_stderr=False,
            )
        self.assertEqual(failure.exception.returncode, 7)
        self.assertEqual(failure.exception.stdout, "result\n")
        self.assertEqual(failure.exception.stderr, "failure\n")

    def test_default_capture_retains_merged_diagnostics(self):
        result = run(
            [sys.executable, "-c", "import sys; print('diagnostic', file=sys.stderr)"],
            capture=True,
        )
        self.assertEqual(result.stdout, "diagnostic\n")
        self.assertIsNone(result.stderr)


class GoDistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="arboresce-go-provenance-")
        self.addCleanup(self.temporary.cleanup)
        self.sdk = Path(self.temporary.name)
        self.module = self.sdk / "bindings/go"
        self.module.mkdir(parents=True)
        (self.sdk / "crates/ffi").mkdir(parents=True)
        (self.sdk / "Cargo.toml").write_text(
            '[workspace.dependencies.arboresce]\nrev = "' + "a" * 40 + '"\n'
        )
        (self.sdk / "rust-toolchain.toml").write_text(
            '[toolchain]\nchannel = "1.98.1"\n'
        )
        (self.module / "go.mod").write_text("module arboresce.ai\n\ngo 1.27.1\n")
        self.generator = {
            "version": "test",
            "revision": "b" * 40,
            "repository": "https://example.invalid/generator",
            "uniffi": "test",
        }
        (self.sdk / "crates/ffi/go-bindgen.json").write_text(json.dumps(self.generator))
        self.policy = {
            "platforms": {
                "darwin_arm64": "aarch64-apple-darwin",
                "linux_amd64": "x86_64-unknown-linux-gnu",
            },
            "source_files": [
                "Cargo.toml",
                "rust-toolchain.toml",
                "crates/ffi/go-bindgen.json",
                "bindings/go/native-platforms.json",
                "bindings/go/go.mod",
            ],
            "package_files": ["go.mod", "native-platforms.json"],
        }
        (self.module / "native-platforms.json").write_text(json.dumps(self.policy))
        self.receipts = []
        self.archives = []
        for target_platform, target in self.policy["platforms"].items():
            archive = (
                self.module
                / f"internal/native/lib/{target_platform}/libarboresce_ffi.a"
            )
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"!<arch>\n")
            receipt = archive.with_name(archive.name + ".json")
            receipt.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "platform": target_platform,
                        "rust_target": target,
                        "profile": "release",
                        "core_rev": "a" * 40,
                        "archive_sha256": digest(archive),
                        "inputs": [
                            {"path": name, "sha256": digest(self.sdk / name)}
                            for name in self.policy["source_files"]
                        ],
                        "generator": self.generator | {"binary_sha256": "c" * 64},
                        "rustc": "rustc 1.98.1 (fixture)",
                    }
                )
            )
            self.archives.append(archive)
            self.receipts.append(receipt)

    def change_receipt(self, **changes):
        receipt = self.receipts[0]
        receipt.write_text(json.dumps(json.loads(receipt.read_text()) | changes))

    def test_complete_archive_is_deterministic_and_excludes_test_sources(self):
        (self.module / "api_test.go").write_text("package arboresce_test\n")
        first = self.sdk / "first.zip"
        second = self.sdk / "second.zip"
        package_go(self.sdk, first, "arboresce.ai@v0.0.0")
        package_go(self.sdk, second, "arboresce.ai@v0.0.0")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    f"arboresce.ai@v0.0.0/{name}"
                    for name in distribution_files(self.sdk)
                },
            )
            self.assertFalse(
                any(name.endswith("_test.go") for name in archive.namelist())
            )

    def test_missing_native_archive_is_rejected(self):
        self.archives[0].unlink()
        with self.assertRaisesRegex(
            ValueError, "Invalid or missing Go distribution file"
        ):
            distribution_files(self.sdk)

    def test_go_proxy_uses_the_vanity_module_identity(self):
        files = distribution_files(self.sdk)
        root = self.sdk / "proxy"
        write_go_proxy(files, root, "0.0.0")
        proxy = root / "arboresce.ai/@v"
        self.assertEqual(
            {path.name for path in proxy.iterdir()},
            {"v0.0.0.zip", "v0.0.0.mod", "v0.0.0.info", "list"},
        )
        self.assertEqual(
            (proxy / "v0.0.0.mod").read_bytes(), files["go.mod"].read_bytes()
        )
        self.assertEqual(
            json.loads((proxy / "v0.0.0.info").read_text())["Version"], "v0.0.0"
        )
        with zipfile.ZipFile(proxy / "v0.0.0.zip") as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"arboresce.ai@v0.0.0/" + name for name in files},
            )

    def test_corrupt_native_archive_is_rejected(self):
        self.archives[0].write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "Stale or corrupt"):
            distribution_files(self.sdk)

    def test_changed_input_is_rejected(self):
        (self.module / "go.mod").write_text("module example.invalid/wrong\n")
        with self.assertRaisesRegex(ValueError, "Stale or corrupt"):
            distribution_files(self.sdk)

    def test_wrong_generator_revision_is_rejected(self):
        self.change_receipt(
            generator=self.generator | {"revision": "d" * 40, "binary_sha256": "c" * 64}
        )
        with self.assertRaisesRegex(ValueError, "Wrong Go generator provenance"):
            distribution_files(self.sdk)

    def test_inconsistent_generator_binary_is_rejected(self):
        self.change_receipt(generator=self.generator | {"binary_sha256": "d" * 64})
        with self.assertRaisesRegex(ValueError, "inconsistent generator binaries"):
            distribution_files(self.sdk)

    def test_wrong_compiler_is_rejected(self):
        self.change_receipt(rustc="rustc 1.98.0 (fixture)")
        with self.assertRaisesRegex(ValueError, "Wrong Rust toolchain"):
            distribution_files(self.sdk)

    def test_symlinked_archive_is_rejected(self):
        archive = self.archives[0]
        target = self.sdk / "external.a"
        archive.rename(target)
        archive.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Invalid or missing"):
            distribution_files(self.sdk)


if __name__ == "__main__":
    unittest.main()
