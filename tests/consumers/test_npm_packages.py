import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from package_tools import (
    NATIVE_NPM_LICENSES,
    SDK,
    pack_npm,
    prepare_native_npm,
    validate_native_npm_archive,
    validate_native_npm_manifest,
)


class NativeNpmPackages(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arboresce-npm-layout-")
        self.addCleanup(temporary.cleanup)
        self.sdk = Path(temporary.name)
        for name in (
            "Cargo.toml",
            "package.json",
            "tests/platforms/targets.py",
            "tests/platforms/targets.json",
            "bindings/go/native-platforms.json",
            "bindings/typescript/package.json",
            "bindings/typescript/LICENSE-MIT",
            "bindings/typescript/LICENSE-APACHE",
        ):
            path = self.sdk / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SDK / name, path)
        self.source = self.sdk / "bindings/typescript"
        (self.sdk / "node_modules").symlink_to(
            SDK / "node_modules", target_is_directory=True
        )
        self.metadata = json.loads((self.source / "package.json").read_text())
        self.policy = json.loads(
            (self.sdk / "tests/platforms/targets.json").read_text()
        )

    def test_fresh_bootstrap_does_not_resolve_unpublished_sdk_packages(self):
        bootstrap = self.sdk / "bootstrap"
        bootstrap.mkdir()
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(SDK / name, bootstrap / name)
        facade = bootstrap / "bindings/typescript"
        facade.mkdir(parents=True)
        metadata = self.metadata | {
            "version": "999.0.0",
            "optionalDependencies": {
                name: "999.0.0" for name in self.metadata["optionalDependencies"]
            },
        }
        (facade / "package.json").write_text(json.dumps(metadata))
        (bootstrap / ".npmrc").write_text("@arboresce:registry=http://127.0.0.1:9/\n")
        subprocess.run(
            [
                "npm",
                "ci",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                "--cache",
                str(bootstrap / "cache"),
            ],
            cwd=bootstrap,
            check=True,
            timeout=120,
            capture_output=True,
        )
        self.assertFalse((bootstrap / "node_modules/@arboresce").exists())
        self.assertEqual(
            json.loads(
                (bootstrap / "node_modules/@napi-rs/cli/package.json").read_text()
            )["version"],
            json.loads((bootstrap / "package.json").read_text())["devDependencies"][
                "@napi-rs/cli"
            ],
        )

    def test_generator_preserves_source_and_produces_only_active_packages(self):
        original = (self.source / "package.json").read_bytes()
        packages = prepare_native_npm(self.sdk)
        self.assertEqual(set(packages), set(self.metadata["optionalDependencies"]))
        self.assertEqual((self.source / "package.json").read_bytes(), original)
        self.assertFalse((self.source / "npm").exists())
        for name, directory in packages.items():
            self.assertEqual(directory.name, name.removeprefix("@arboresce/native-"))
            for license_name, packaged_name in NATIVE_NPM_LICENSES.items():
                self.assertEqual(
                    (directory / packaged_name).read_bytes(),
                    (self.source / license_name).read_bytes(),
                )

    def test_regeneration_removes_stale_targets_and_binaries(self):
        packages = prepare_native_npm(self.sdk)
        staging = self.sdk / "build/typescript/npm"
        stale = staging / "win32-x64-msvc"
        stale.mkdir()
        (stale / "package.json").write_text("{}")
        binary = next(iter(packages.values())) / "stale.node"
        binary.write_bytes(b"old binary")
        prepare_native_npm(self.sdk)
        self.assertFalse(stale.exists())
        self.assertFalse(binary.exists())

    def test_undeclared_build_target_is_rejected(self):
        self.metadata["napi"]["targets"].append("x86_64-pc-windows-msvc")
        (self.source / "package.json").write_text(json.dumps(self.metadata))
        with self.assertRaisesRegex(ValueError, "napi build targets differ"):
            prepare_native_npm(self.sdk)

    def test_source_version_drift_cannot_regenerate_matching_wrong_packages(self):
        self.metadata["version"] = "9.0.0"
        (self.source / "package.json").write_text(json.dumps(self.metadata))
        with self.assertRaisesRegex(ValueError, "metadata differs.*version"):
            prepare_native_npm(self.sdk)

    def test_generated_metadata_must_match_distribution_contract(self):
        packages = prepare_native_npm(self.sdk)
        item = self.policy["node_packages"]["linux-x64"]
        target = self.policy["platforms"]["linux-x64"]
        manifest = json.loads((packages[item["name"]] / "package.json").read_text())
        for key, value in (
            ("version", "9.0.0"),
            ("cpu", ["arm64"]),
            ("os", ["darwin"]),
            ("libc", ["musl"]),
            ("engines", {"node": ">=1"}),
            ("main", "wrong.node"),
        ):
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "metadata differs"),
            ):
                validate_native_npm_manifest(
                    manifest | {key: value}, item, target, self.metadata
                )

    def test_archive_contains_exact_metadata_licenses_and_binary(self):
        packages = prepare_native_npm(self.sdk)
        directory = next(iter(packages.values()))
        manifest = json.loads((directory / "package.json").read_text())
        native = self.source / "native"
        native.mkdir()
        binary = native / manifest["main"]
        binary.write_bytes(b"native fixture")
        shutil.copyfile(binary, directory / binary.name)
        artifact = pack_npm(directory, self.sdk, NATIVE_NPM_LICENSES.values())
        validate_native_npm_archive(artifact, directory, self.source)
        binary.write_bytes(b"different native fixture")
        with self.assertRaisesRegex(ValueError, "contents differ"):
            validate_native_npm_archive(artifact, directory, self.source)


if __name__ == "__main__":
    unittest.main()
