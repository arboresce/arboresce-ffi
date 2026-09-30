import plistlib
import shutil
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

import swift_packages


class SwiftPackages(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arb-swift-package-tests-")
        self.addCleanup(temporary.cleanup)
        self.sdk = Path(temporary.name)
        (self.sdk / "Cargo.toml").write_text('[workspace.package]\nversion = "0.0.0"\n')
        self.staged = self.sdk / "build/swift-dev"
        self.staged.mkdir(parents=True)
        for name in ("Sources", "Tests", "dev"):
            shutil.copytree(
                swift_packages.SDK / "bindings/swift" / name,
                self.sdk / "bindings/swift" / name,
            )
        for name in ("Sources", "Tests"):
            shutil.copytree(self.sdk / "bindings/swift" / name, self.staged / name)
        shutil.copyfile(
            self.sdk / "bindings/swift/dev/Package.swift", self.staged / "Package.swift"
        )
        for name in ("README.md", "LICENSE-MIT", "LICENSE-APACHE"):
            (self.staged / name).write_text(name)
        framework = self.sdk / "build/swift/Arboresce.xcframework"
        framework.mkdir(parents=True)
        (framework / "Info.plist").write_bytes(b"fixture framework")
        shutil.copytree(framework, self.staged / "Arboresce.xcframework")

    def test_framework_metadata_is_stable_across_library_order(self):
        manifest = self.sdk / "build/swift/Arboresce.xcframework/Info.plist"
        libraries = [
            {
                "LibraryIdentifier": "macos",
                "SupportedArchitectures": ["x86_64", "arm64"],
            },
            {"LibraryIdentifier": "ios", "SupportedArchitectures": ["arm64"]},
        ]
        value = {"AvailableLibraries": libraries, "XCFrameworkFormatVersion": "1.0"}
        manifest.write_bytes(plistlib.dumps(value))
        swift_packages.normalize_framework(self.sdk)
        original = manifest.read_bytes()
        libraries.reverse()
        libraries[1]["SupportedArchitectures"].reverse()
        manifest.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY))
        swift_packages.normalize_framework(self.sdk)
        self.assertEqual(manifest.read_bytes(), original)
        swift_packages.normalize_framework(self.sdk)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual(plistlib.loads(original)["XCFrameworkFormatVersion"], "1.0")

    def test_framework_metadata_rejects_duplicate_libraries(self):
        manifest = self.sdk / "build/swift/Arboresce.xcframework/Info.plist"
        library = {"LibraryIdentifier": "ios", "SupportedArchitectures": ["arm64"]}
        manifest.write_bytes(plistlib.dumps({"AvailableLibraries": [library, library]}))
        with self.assertRaisesRegex(ValueError, "Duplicate framework library"):
            swift_packages.normalize_framework(self.sdk)

    def test_framework_metadata_rejects_symlink(self):
        manifest = self.sdk / "build/swift/Arboresce.xcframework/Info.plist"
        manifest.unlink()
        manifest.symlink_to(self.sdk / "Cargo.toml")
        with self.assertRaisesRegex(ValueError, "Unsupported Swift package input"):
            swift_packages.normalize_framework(self.sdk)

    def test_framework_metadata_rejects_symlinked_framework(self):
        framework = self.sdk / "build/swift/Arboresce.xcframework"
        external = self.sdk / "external-framework"
        framework.rename(external)
        framework.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Unsupported Swift framework symlink"):
            swift_packages.normalize_framework(self.sdk)

    def test_package_is_deterministic_and_excludes_local_cache(self):
        (self.staged / ".build").mkdir()
        (self.staged / ".build/private-cache").write_bytes(b"local cache")
        artifact = swift_packages.package_swift(self.sdk)
        original = artifact.read_bytes()
        self.assertEqual(swift_packages.package_swift(self.sdk).read_bytes(), original)
        with zipfile.ZipFile(artifact) as archive:
            self.assertFalse(any(".build" in name for name in archive.namelist()))
        with zipfile.ZipFile(artifact.parent / "Arboresce.xcframework.zip") as archive:
            self.assertEqual(archive.namelist(), ["Arboresce.xcframework/Info.plist"])
        extracted = swift_packages.extract_package(
            artifact, self.sdk / "relocated package", "0.0.0"
        )
        self.assertEqual(
            (extracted / "Package.swift").read_bytes(),
            (self.staged / "Package.swift").read_bytes(),
        )

    def test_rejects_stale_source_and_manifest(self):
        source = self.staged / "Sources/Arboresce/Arboresce.swift"
        source.write_text("stale")
        with self.assertRaisesRegex(ValueError, "Stale staged Swift Sources"):
            swift_packages.package_swift(self.sdk)
        shutil.copyfile(
            self.sdk / "bindings/swift/Sources/Arboresce/Arboresce.swift", source
        )
        (self.staged / "Package.swift").write_text("stale")
        with self.assertRaisesRegex(ValueError, "Staged Swift manifest differs"):
            swift_packages.package_swift(self.sdk)

    def test_rejects_symlink_and_unexpected_root_inputs(self):
        extra = self.staged / "receipt.txt"
        extra.write_text("private build receipt")
        with self.assertRaisesRegex(ValueError, "Unexpected staged"):
            swift_packages.package_swift(self.sdk)
        extra.unlink()
        local_state = self.staged / "Sources/.DS_Store"
        local_state.write_bytes(b"local state")
        with self.assertRaisesRegex(ValueError, "Local state"):
            swift_packages.package_swift(self.sdk)
        local_state.unlink()
        (self.staged / "Sources/external.swift").symlink_to(self.sdk / "Cargo.toml")
        with self.assertRaisesRegex(ValueError, "Unsupported Swift package input"):
            swift_packages.package_swift(self.sdk)

    def test_rejects_unsafe_archive_before_extracting(self):
        artifact = swift_packages.package_swift(self.sdk)
        data = artifact.read_bytes()
        for name, mode in (
            ("../escape", stat.S_IFREG),
            ("arboresce-swift-0.0.0/Sources/link", stat.S_IFLNK),
            ("arboresce-swift-0.0.0/Package.swift", stat.S_IFREG),
            ("arboresce-swift-0.0.0/.build/cache", stat.S_IFREG),
        ):
            with self.subTest(name=name):
                artifact.write_bytes(data)
                with (
                    warnings.catch_warnings(),
                    zipfile.ZipFile(artifact, "a") as archive,
                ):
                    warnings.simplefilter("ignore", UserWarning)
                    entry = zipfile.ZipInfo(name)
                    entry.external_attr = (mode | 0o644) << 16
                    archive.writestr(entry, b"invalid")
                destination = self.sdk / "must-not-exist"
                with self.assertRaises(ValueError):
                    swift_packages.extract_package(artifact, destination, "0.0.0")
                self.assertFalse(destination.exists())
