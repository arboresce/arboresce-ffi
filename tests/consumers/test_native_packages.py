import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import native_packages as native

SDK = Path(__file__).resolve().parents[2]


class NativeArtifacts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="arboresce-native-artifacts-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sdk = self.root / "sdk"
        for name in native.source_inputs(SDK):
            destination = self.sdk / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SDK / name, destination)
        self.stage = self.sdk / "build/native/stage"
        self.stage.mkdir(parents=True)
        self.shared, self.alias = native.library_names()
        (self.stage / "libarboresce_c.a").write_bytes(b"!<arch>\nfixture")
        (self.stage / self.shared).write_bytes(b"synthetic shared artifact")
        (self.stage / "native-static-libs.txt").write_text("-lc -lm\n")
        compiler = native.identity(self.sdk)["compiler_pin"]
        tools = {
            "rust": f"rustc {compiler} (fixture)\nhost: {native.host_target()}",
            "c": "C fixture",
            "cmake": "CMake fixture",
            "generator": "cbindgen 0.29.4",
        }
        tool_patch = patch.object(native, "tool_identity", return_value=tools)
        tool_patch.start()
        self.addCleanup(tool_patch.stop)
        with patch.object(native, "verify_native_artifacts"):
            native.record_build(self.sdk)
        self.prefix = self.sdk / "build/native/install"
        for kind in ("c", "cpp"):
            for name in native.installed_files(kind):
                destination = self.prefix / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if name.startswith("include/"):
                    shutil.copyfile(self.sdk / "bindings" / kind / name, destination)
                elif name.startswith("lib/lib"):
                    source = self.stage / (
                        self.shared if name.endswith(self.alias) else Path(name).name
                    )
                    shutil.copyfile(source, destination)
                elif "LICENSE" in name:
                    shutil.copyfile(
                        self.sdk / "bindings" / kind / Path(name).name, destination
                    )
                elif name.endswith(".md"):
                    destination.write_bytes(native.documentation(self.sdk, kind)[name])
                else:
                    destination.write_text('prefix="${PACKAGE_PREFIX_DIR}/lib"\n')
        alias = self.prefix / "lib" / self.alias
        alias.unlink()
        alias.symlink_to(self.shared)

    def package(self, kind="c", filename=None):
        return native.package_native(
            self.sdk, self.root / (filename or kind + ".zip"), kind
        )

    def rewrite_archive(self, archive, transform):
        with zipfile.ZipFile(archive) as original:
            files = {
                entry.filename: (entry, original.read(entry.filename))
                for entry in original.infolist()
            }
        transform(files)
        with zipfile.ZipFile(archive, "w") as rewritten:
            for entry, content in files.values():
                rewritten.writestr(entry, content)

    def test_deterministic_allowlisted_archives_and_matching_dependency(self):
        first, second = self.package(filename="a.zip"), self.package(filename="b.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        cpp = self.package("cpp")
        destination = self.root / "install"
        native.extract_native(self.sdk, first, "c", destination)
        native.extract_native(self.sdk, cpp, "cpp", destination)
        self.assertFalse((destination / "lib" / self.alias).is_symlink())
        self.assertEqual(
            (destination / "lib" / self.alias).read_bytes(),
            (destination / "lib" / self.shared).read_bytes(),
        )
        with zipfile.ZipFile(cpp) as archive:
            self.assertEqual(set(archive.namelist()), native.archive_files("cpp"))
            self.assertFalse(
                any(
                    name.endswith((".a", ".so", ".dylib"))
                    for name in archive.namelist()
                )
            )

    def route_build(self):
        build = self.sdk / "build"
        destination = self.root / "routed-build"
        shutil.move(build, destination)
        build.symlink_to(destination, target_is_directory=True)

    def test_routed_build_preserves_c_and_cpp_package_bytes(self):
        expected = {kind: self.package(kind).read_bytes() for kind in ("c", "cpp")}
        self.route_build()
        for kind, content in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(self.package(kind).read_bytes(), content)

    def test_routed_build_rejects_symlinked_native_directory(self):
        self.route_build()
        directory = self.sdk / "build/native"
        destination = self.root / "native-alias"
        shutil.move(directory, destination)
        directory.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinked native package directory"):
            self.package()

    def test_routed_build_rejects_symlinked_receipt(self):
        self.route_build()
        receipt = self.sdk / "build/native/build-receipt.json"
        destination = self.root / "receipt.json"
        shutil.move(receipt, destination)
        receipt.symlink_to(destination)
        with self.assertRaisesRegex(ValueError, "Invalid native library alias"):
            self.package()

    def test_routed_build_rejects_changed_tool_identity(self):
        self.route_build()
        with patch.object(native, "tool_identity", return_value={"rust": "changed"}):
            with self.assertRaisesRegex(ValueError, "Stale"):
                self.package()

    def test_routed_build_rejects_changed_staged_artifact(self):
        self.route_build()
        (self.stage / "libarboresce_c.a").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Corrupt native build artifacts"):
            self.package()

    def test_extra_installed_file_is_rejected(self):
        (self.prefix / "lib/unexpected.so").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.package()

    def test_safety_documentation_is_bundled_and_bound_to_sources(self):
        for kind in ("c", "cpp"):
            with self.subTest(kind=kind):
                archive = self.package(kind)
                with zipfile.ZipFile(archive) as package:
                    for name, content in native.documentation(self.sdk, kind).items():
                        self.assertEqual(package.read(name), content)
                    readme = package.read(f"share/arboresce-{kind}/README.md")
                    self.assertNotIn(b"../../DEVELOPERS.md", readme)
                    self.assertIn(b"DEVELOPERS.md", readme)
        (self.prefix / "share/arboresce-c/DEVELOPERS.md").write_text(
            "wrong safety contract"
        )
        with self.assertRaisesRegex(ValueError, "documentation"):
            self.package()

    def test_target_override_cannot_repackage_stale_default_artifacts(self):
        for ambient_target, flag_environment in (
            (
                native.host_target(),
                {"CARGO_ENCODED_RUSTFLAGS": "--cfg=retained_flag\x1f-Cpanic=abort"},
            ),
            (
                "different-ambient-target",
                {"RUSTFLAGS": "--cfg=retained_flag -Cpanic=abort"},
            ),
        ):
            with self.subTest(ambient_target=ambient_target):
                root = self.root / ambient_target
                result = subprocess.run(
                    [
                        "bash",
                        str(SDK / "tests/consumers/fixtures/native_target.sh"),
                        str(root),
                        str(SDK / "scripts/native.sh"),
                        native.host_target(),
                    ],
                    env=dict(
                        {
                            key: value
                            for key, value in os.environ.items()
                            if key not in {"CARGO_ENCODED_RUSTFLAGS", "RUSTFLAGS"}
                        },
                        CARGO_BUILD_TARGET=ambient_target,
                        **flag_environment,
                    ),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(
                    (root / "selected-target").read_text().strip(), native.host_target()
                )
                flags = (root / "rust-flags").read_text().split("\x1f")
                self.assertEqual(flags[:2], ["--cfg=retained_flag", "-Cpanic=abort"])
                observed = subprocess.check_output(
                    ["rustc", *flags, "--print", "cfg"], text=True
                )
                self.assertIn('panic="unwind"', observed.splitlines())
                self.assertEqual(
                    flags[-2:], ["-Crelocation-model=pic", "-Cpanic=unwind"]
                )
                self.assertIn(f"--remap-path-prefix={root}=/src/arboresce-ffi", flags)
                for name in ("libarboresce_c.a", self.shared):
                    self.assertEqual(
                        (root / "build/native/stage" / name).read_bytes(),
                        b"fresh explicit host artifact",
                    )

    def test_missing_installed_file_is_rejected(self):
        (self.prefix / "include/arboresce/export.h").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            self.package()

    def test_corrupt_installed_library_is_rejected(self):
        (self.prefix / "lib/libarboresce_c.a").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs from build receipt"):
            self.package()

    def test_stale_source_is_rejected(self):
        self.route_build()
        source = self.sdk / "crates/c/src/lib.rs"
        source.write_text(source.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.package()

    def test_wrong_build_host_is_rejected(self):
        self.route_build()
        receipt = self.sdk / "build/native/build-receipt.json"
        receipt.write_text(
            json.dumps(json.loads(receipt.read_text()) | {"target": "wrong-host"})
        )
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.package()

    def test_absolute_or_escaping_alias_is_rejected(self):
        alias = self.prefix / "lib" / self.alias
        for target in (
            str(self.prefix / "lib" / self.shared),
            "../../../outside",
            self.alias,
        ):
            with self.subTest(target=target):
                alias.unlink()
                alias.symlink_to(target)
                with self.assertRaisesRegex(ValueError, "alias"):
                    self.package()

    def test_absolute_cmake_path_is_rejected(self):
        (self.prefix / "lib/cmake/Arboresce/ArboresceTargets.cmake").write_text(
            'set(location "/tmp/unportable/library")'
        )
        with self.assertRaisesRegex(ValueError, "Absolute"):
            self.package()

    def test_archive_corruption_is_rejected(self):
        archive = self.package()

        def corrupt(files):
            entry, _ = files["lib/libarboresce_c.a"]
            files[entry.filename] = (entry, b"corrupt")

        self.rewrite_archive(archive, corrupt)
        with self.assertRaisesRegex(ValueError, "Corrupt"):
            native.validate_archive(self.sdk, archive, "c")

    def test_traversal_and_absolute_zip_paths_are_rejected(self):
        for name in ("../escape", "/tmp/escape", "include//bad", "include\\bad"):
            with self.subTest(name=name):
                archive = self.package()
                with zipfile.ZipFile(archive, "a") as output:
                    output.writestr(name, b"bad")
                with self.assertRaises(ValueError):
                    native.validate_archive(self.sdk, archive, "c")

    def test_cpp_requires_the_exact_c_package(self):
        c_archive, cpp_archive = self.package(), self.package("cpp")
        destination = self.root / "install"
        native.extract_native(self.sdk, c_archive, "c", destination)
        (destination / native.manifest_path("c")).write_text("{}")
        with self.assertRaisesRegex(ValueError, "dependency"):
            native.extract_native(self.sdk, cpp_archive, "cpp", destination)

    def test_wrong_archive_abi_host_and_compiler_are_rejected(self):
        for field, value in (
            ("target", "wrong"),
            ("abi", {}),
            ("compiler_pin", "1.98.0"),
        ):
            with self.subTest(field=field):
                archive = self.package()

                def change_manifest(files):
                    name = native.manifest_path("c")
                    entry, content = files[name]
                    manifest = json.loads(content)
                    manifest[field] = value
                    files[name] = (entry, native.canonical(manifest))

                self.rewrite_archive(archive, change_manifest)
                with self.assertRaisesRegex(ValueError, "identity"):
                    native.validate_archive(self.sdk, archive, "c")

    def test_duplicate_zip_paths_are_rejected(self):
        archive = self.package()
        with self.assertWarns(UserWarning):
            with zipfile.ZipFile(archive, "a") as output:
                entry = output.getinfo("include/arboresce/export.h")
                output.writestr(entry, b"duplicate")
        with self.assertRaisesRegex(ValueError, "inventory"):
            native.validate_archive(self.sdk, archive, "c")

    def test_extraction_refuses_symlinks_and_existing_files(self):
        archive = self.package()
        destination = self.root / "install"
        native.extract_native(self.sdk, archive, "c", destination)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            native.extract_native(self.sdk, archive, "c", destination)
        linked = self.root / "linked"
        linked.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            native.extract_native(self.sdk, archive, "c", linked)
