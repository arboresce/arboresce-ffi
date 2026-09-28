import contextlib
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import android_elf
import packaged
import runtime_evidence
import swift_package
import test_android
import test_go_platforms
import test_ios


class RuntimeEvidence(unittest.TestCase):
    def test_collection_is_optional_and_preserves_actual_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "runtime.jsonl"
            with patch.dict(os.environ, {}, clear=True):
                entry = runtime_evidence.record(
                    "swift",
                    "ios-sim-arm64",
                    "simulator",
                    {"runtime": "iOS-26-0"},
                    cpu="arm64",
                )
            self.assertFalse(destination.exists())
            self.assertFalse(entry["minimum_runtime"])
            with patch.dict(
                os.environ,
                {
                    "ARBORESCE_TEST_EVIDENCE": str(destination),
                    "ARBORESCE_TEST_SUITE": "mobile",
                },
            ):
                runtime_evidence.record(
                    "android",
                    "android-arm64",
                    "emulator",
                    {"api": 36, "page_size": 16384},
                    cpu="arm64",
                )
            saved = json.loads(destination.read_text())
            self.assertEqual(saved["runtime"], {"api": 36, "page_size": 16384})
            self.assertEqual(saved["suite"], "mobile")
            self.assertEqual(saved["execution"], "emulator")

    def test_container_mode_uses_docker_engine_architecture(self):
        with (
            patch(
                "runtime_evidence.subprocess.check_output",
                side_effect=[
                    "aarch64\n",
                    "owned-container\n",
                    "sha256:actual-image\n",
                    "x86_64\nLinux\nglibc 2.36\n",
                ],
            ) as commands,
            patch("runtime_evidence.subprocess.run") as cleanup,
        ):
            mode, runtime = runtime_evidence.container_runtime("image:pinned", "amd64")
        self.assertEqual(mode, "container-emulated")
        self.assertEqual(runtime["image_id"], "sha256:actual-image")
        self.assertEqual(
            commands.call_args_list[2].args[0],
            ["docker", "inspect", "--format", "{{.Image}}", "owned-container"],
        )
        cleanup.assert_called_once_with(
            ["docker", "rm", "--force", "owned-container"],
            check=True,
            capture_output=True,
        )


class GoModuleInput(unittest.TestCase):
    def archive(self, path, entries):
        with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name, value in entries:
                archive.writestr(name, value)

    def test_rejects_changed_missing_extra_and_duplicate_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated, supplied = root / "generated.zip", root / "supplied.zip"
            expected = [("arboresce.ai@v0.0.0/go.mod", b"module arboresce.ai")]
            self.archive(generated, expected)
            before = generated.read_bytes()
            for entries in (
                [],
                expected * 2,
                [(expected[0][0], b"changed")],
                expected + [("extra", b"")],
            ):
                with self.subTest(entries=entries):
                    self.archive(supplied, entries)
                    with self.assertRaises(ValueError):
                        test_go_platforms.copy_module_zip(supplied, generated)
                    self.assertEqual(generated.read_bytes(), before)

    def test_consumes_validated_snapshot_despite_external_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated, supplied = root / "generated.zip", root / "supplied.zip"
            entries = [("arboresce.ai@v0.0.0/go.mod", b"module arboresce.ai")]
            self.archive(generated, entries)
            self.archive(supplied, entries)
            with zipfile.ZipFile(supplied, "a") as archive:
                archive.comment = b"retained canonical metadata"
            expected = supplied.read_bytes()
            original = Path.write_bytes

            def replace(path, content):
                original(supplied, b"replaced external input")
                return original(path, content)

            with patch.object(Path, "write_bytes", replace):
                test_go_platforms.copy_module_zip(supplied, generated)
            self.assertEqual(generated.read_bytes(), expected)
            self.assertEqual(supplied.read_bytes(), b"replaced external input")

    def test_isolates_hostile_go_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(
                os.environ,
                {
                    "GOFLAGS": "-modfile=/tmp/other.mod -overlay=/tmp/other.json",
                    "GOTOOLCHAIN": "go1.99.0+auto",
                    "GOPROXY": "https://unrelated.invalid",
                    "GOMODCACHE": "/tmp/ambient-cache",
                },
            ):
                env = test_go_platforms.consumer_environment(
                    root, root / "proxy", "linux", "amd64", "cc"
                )
            self.assertEqual(env["GOFLAGS"], "")
            self.assertEqual(env["GOTOOLCHAIN"], "local")
            self.assertEqual(env["GOPROXY"], (root / "proxy").as_uri())
            self.assertEqual(env["GOMODCACHE"], str(root / "cache-linux-amd64"))


class AndroidSelection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arb-mobile-helpers-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def image(self, api, tag, abi):
        path = (
            self.root
            / "system-images"
            / f"android-{api}"
            / tag
            / abi
            / "source.properties"
        )
        path.parent.mkdir(parents=True)
        path.write_text(
            f"AndroidVersion.ApiLevel={api}\nSystemImage.Abi={abi}\nSystemImage.TagId={tag}\n"
        )

    def test_selects_installed_16k_image_for_host(self):
        self.image(36, "google_apis", "arm64-v8a")
        self.image(35, "google_apis_ps16k", "arm64-v8a")
        self.image(36, "google_apis_ps16k", "x86_64")
        self.assertEqual(
            test_android.select_android_image(self.root, "arm64"),
            "system-images;android-35;google_apis_ps16k;arm64-v8a",
        )
        self.assertEqual(
            test_android.select_android_image(self.root, "x86_64"),
            "system-images;android-36;google_apis_ps16k;x86_64",
        )

    def test_ordinary_or_wrong_architecture_image_is_not_qualification(self):
        self.image(36, "google_apis", "arm64-v8a")
        self.image(36, "google_apis_ps16k", "x86_64")
        with self.assertRaisesRegex(ValueError, "Install.*16 KB"):
            test_android.select_android_image(self.root, "arm64")

    def test_accepts_sdk_metadata_with_separate_page_size_tag(self):
        self.image(36, "google_apis_ps16k", "arm64-v8a")
        properties = (
            self.root
            / "system-images/android-36/google_apis_ps16k/arm64-v8a/source.properties"
        )
        properties.write_text(
            "AndroidVersion.ApiLevel=36\nSystemImage.Abi=arm64-v8a\n"
            "SystemImage.TagId=google_apis,page_size_16kb\n"
            "SystemImage.TagDisplay=Google APIs,16 KB Page Size\n"
        )
        self.assertEqual(
            test_android.select_android_image(self.root, "arm64"),
            "system-images;android-36;google_apis_ps16k;arm64-v8a",
        )

    def test_requires_observed_16k_page_size(self):
        self.assertEqual(test_android.require_page_size("16384\n"), 16384)
        for value in ("4096", "", "not found"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                test_android.require_page_size(value)

    def test_port_ownership_survives_socket_handoff(self):
        with test_android.reserve_emulator_port(self.root) as (first, release):
            release()
            with self.assertRaisesRegex(ValueError, "No free"):
                with test_android.reserve_emulator_port(self.root, (first,)):
                    self.fail("Port ownership lock was ignored")
            with test_android.reserve_emulator_port(self.root) as (second, _):
                self.assertNotEqual(first, second)
        with test_android.reserve_emulator_port(self.root, (first,)) as (again, _):
            self.assertEqual(first, again)

    def test_port_selection_preserves_other_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(ValueError, "No free"):
                with test_android.reserve_emulator_port(self.root, (port,)):
                    self.fail("Port already held by another process was selected")
            self.assertEqual(listener.getsockname()[1], port)


class AndroidLibraries(unittest.TestCase):
    def elf(self, alignment=16384, address=0):
        data = bytearray(120)
        data[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", data, 18, 183)
        struct.pack_into("<Q", data, 32, 64)
        struct.pack_into("<HH", data, 54, 56, 1)
        struct.pack_into("<I", data, 64, 1)
        struct.pack_into("<Q", data, 80, address)
        struct.pack_into("<Q", data, 112, alignment)
        return bytes(data)

    def archive(self, entries):
        storage = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(storage, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name, data in entries:
                archive.writestr(name, data)
        return zipfile.ZipFile(storage)

    def test_checks_jna_as_well_as_rust(self):
        names = ("lib/arm64-v8a/libarboresce_ffi.so", "lib/arm64-v8a/libjnidispatch.so")
        with self.archive([(name, self.elf()) for name in names]) as archive:
            self.assertEqual(
                android_elf.check_apk_native(archive, ("arm64-v8a",)),
                {"arm64-v8a": ["libarboresce_ffi.so", "libjnidispatch.so"]},
            )
        with self.archive(
            [(names[0], self.elf()), (names[1], self.elf(4096))]
        ) as archive:
            with self.assertRaisesRegex(ValueError, "Insufficient ELF"):
                android_elf.check_apk_native(archive, ("arm64-v8a",))

    def test_rejects_duplicates_missing_jna_and_unexpected_inventory(self):
        name = "lib/arm64-v8a/libarboresce_ffi.so"
        for entries, expected in (
            ([(name, self.elf())] * 2, "Duplicate"),
            ([(name, self.elf())], "missing"),
            ([], "inventory"),
        ):
            with self.subTest(expected=expected), self.archive(entries) as archive:
                with self.assertRaisesRegex(ValueError, expected):
                    android_elf.check_apk_native(archive, ("arm64-v8a",))

    def test_rejects_truncated_and_incongruent_elf(self):
        for data in (b"", b"\x7fELF", self.elf()[:80], self.elf(address=4096)):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                android_elf.check_elf(data, "arm64-v8a", 16384)


class IOSSelection(unittest.TestCase):
    def runtime(self, version, architecture="arm64", available=True):
        return {
            "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-"
            + version.replace(".", "-"),
            "version": version,
            "isAvailable": available,
            "supportedArchitectures": [architecture],
            "supportedDeviceTypes": [{"identifier": "compatible"}],
        }

    def device(self, identifier="compatible", minimum="17.0"):
        return {
            "identifier": identifier,
            "productFamily": "iPhone",
            "minRuntimeVersionString": minimum,
            "maxRuntimeVersionString": "65535.255.255",
        }

    def test_selects_compatible_runtime_device_and_architecture(self):
        runtimes = [
            self.runtime("26.5"),
            self.runtime("27.0", available=False),
            self.runtime("28.0", "x86_64"),
        ]
        runtime, device, architecture = test_ios.select_ios_destination(
            runtimes, [self.device(), self.device("newest-only", "30.0")], "arm64"
        )
        self.assertEqual(
            (runtime, device, architecture),
            ("com.apple.CoreSimulator.SimRuntime.iOS-26-5", "compatible", "arm64"),
        )

    def test_rejects_missing_or_incompatible_runtime(self):
        for runtimes, devices in (
            ([], [self.device()]),
            ([self.runtime("26.5", "x86_64")], [self.device()]),
            ([self.runtime("26.5")], [self.device(minimum="27.0")]),
        ):
            with (
                self.subTest(runtimes=runtimes),
                self.assertRaisesRegex(ValueError, "Install an available iOS"),
            ):
                test_ios.select_ios_destination(runtimes, devices, "arm64")

    def test_owned_device_cleanup_runs_after_failure(self):
        checked = Mock(side_effect=["owned-uuid", ""])
        with patch.object(test_ios.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "failed"):
                with test_ios.owned_ios_simulator(
                    checked, "runtime", "device"
                ) as device:
                    self.assertEqual(device, "owned-uuid")
                    raise RuntimeError("failed")
            run.assert_called_once_with(
                ["xcrun", "simctl", "shutdown", "owned-uuid"],
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(
            checked.call_args_list[-1].args[0],
            ["xcrun", "simctl", "delete", "owned-uuid"],
        )


class SwiftPackageLayout(unittest.TestCase):
    def test_accepts_source_and_staged_packages_without_external_paths(self):
        for sources, framework in (
            ("Sources", "Arboresce.xcframework"),
            ("bindings/swift/Sources", "build/swift/Arboresce.xcframework"),
        ):
            with (
                self.subTest(sources=sources),
                tempfile.TemporaryDirectory(prefix="arb-swift-layout-") as temporary,
            ):
                root = Path(temporary)
                (root / sources).mkdir(parents=True)
                (root / framework).mkdir(parents=True)
                (root / framework / "Info.plist").write_text("fixture")
                self.assertEqual(
                    swift_package.swift_package_paths(root),
                    (root / sources, root / framework),
                )
                (root / framework / "Info.plist").unlink()
                with self.assertRaisesRegex(ValueError, "Missing Swift"):
                    swift_package.swift_package_paths(root)


class SwiftStaging(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arb-swift-stage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        sdk = Path(__file__).resolve().parents[2]
        for path in ("bindings/swift", "scripts"):
            (self.root / path).mkdir(parents=True)
        for directory in ("Sources", "Tests", "dev"):
            shutil.copytree(
                sdk / "bindings/swift" / directory,
                self.root / "bindings/swift" / directory,
            )
        for name in ("LICENSE-MIT", "LICENSE-APACHE"):
            shutil.copyfile(sdk / name, self.root / name)
        shutil.copyfile(
            sdk / "bindings/swift/README.md", self.root / "bindings/swift/README.md"
        )
        shutil.copyfile(sdk / "scripts/swift.sh", self.root / "scripts/swift.sh")
        framework = self.root / "build/swift/Arboresce.xcframework"
        framework.mkdir(parents=True)
        (framework / "Info.plist").write_text("native artifact fixture")

    def stage(self, accepted=True):
        command = 'set -euo pipefail; check_swift_local() { return "$CHECK_RESULT"; }; die() { exit 1; }; source "$ROOT/scripts/swift.sh"; stage_swift_dev'
        return subprocess.run(
            ["bash", "-c", command],
            env=dict(
                os.environ, ROOT=str(self.root), CHECK_RESULT="0" if accepted else "1"
            ),
            capture_output=True,
            text=True,
        )

    def test_copies_canonical_inputs_and_replaces_stale_sources(self):
        destination = self.root / "build/swift-dev"
        self.assertEqual(self.stage().returncode, 0)
        source = Path("Sources/Arboresce/Arboresce.swift")
        self.assertEqual(
            (destination / source).read_bytes(),
            (self.root / "bindings/swift" / source).read_bytes(),
        )
        self.assertEqual(
            (destination / "Package.swift").read_bytes(),
            (self.root / "bindings/swift/dev/Package.swift").read_bytes(),
        )
        (destination / "Sources/obsolete.swift").write_text("stale")
        (destination / ".build").mkdir()
        (destination / ".build/cache").write_text("cache")
        self.assertEqual(self.stage().returncode, 0)
        self.assertFalse((destination / "Sources/obsolete.swift").exists())
        self.assertEqual((destination / ".build/cache").read_text(), "cache")
        self.assertTrue((destination / "Arboresce.xcframework/Info.plist").is_file())
        self.assertFalse(any(path.is_symlink() for path in destination.rglob("*")))

    def test_failed_receipt_does_not_stage_any_package(self):
        self.assertNotEqual(self.stage(False).returncode, 0)
        self.assertFalse((self.root / "build/swift-dev").exists())


class PackagedPlatformCommands(unittest.TestCase):
    def test_go_module_zip_cannot_be_silently_ignored_by_other_consumers(self):
        with self.assertRaisesRegex(ValueError, "requires the Go consumer"):
            packaged.check("swift", Path("unused"), Path("module.zip"))

    def test_prepared_go_module_zip_is_passed_to_isolated_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, packages, _ = packaged.consumer_tools()
            with (
                patch.object(packages, "extract_zip"),
                patch("packaged.run_suite") as suite,
            ):
                packaged.check("go", root, root / "canonical.zip")
            self.assertEqual(
                suite.call_args.args[1]["module_zip"], root / "canonical.zip"
            )
            self.assertIsNone(packaged.GoPlatforms.module_zip)

    def test_missing_artifacts_fail_without_runtime_or_build_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            for language in (
                "python",
                "typescript",
                "kotlin",
                "go",
                "swift",
                "ios",
                "android",
                "c",
                "cpp",
            ):
                with (
                    self.subTest(language=language),
                    patch("packaged.record") as evidence,
                    patch("packaged.platform.platform", return_value="Synthetic host"),
                    patch(
                        "subprocess.run",
                        side_effect=AssertionError("Unexpected process"),
                    ),
                ):
                    with self.assertRaises(FileNotFoundError):
                        packaged.check(language, Path(temporary))
                    evidence.assert_not_called()

    def test_host_consumers_use_prepared_packages_and_record_only_success(self):
        _, packages, _ = packaged.consumer_tools()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for language, path, action in (
                ("typescript", "npm/arboresce-0.0.0.tgz", "test_typescript_consumer"),
                (
                    "kotlin",
                    "maven/arboresce-0.0.0-central-bundle.zip",
                    "test_kotlin_consumer",
                ),
            ):
                artifact = root / path
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.touch()
                for failure in (False, True):
                    with (
                        self.subTest(language=language, failure=failure),
                        patch.object(
                            packages,
                            action,
                            side_effect=RuntimeError("failed") if failure else None,
                        ) as consume,
                        patch(
                            "packaged.subprocess.check_output",
                            return_value='{"node":"v22.22.3","architecture":"arm64","os":"darwin"}',
                        ),
                        patch(
                            "packaged.subprocess.run",
                            return_value=subprocess.CompletedProcess(
                                [], 0, "", "Java 21\n    os.arch = aarch64\n"
                            ),
                        ),
                        patch("packaged.record") as evidence,
                        patch(
                            "packaged.platform.platform", return_value="Synthetic host"
                        ),
                    ):
                        if failure:
                            with self.assertRaises(RuntimeError):
                                packaged.check(language, root)
                            evidence.assert_not_called()
                        else:
                            packaged.check(language, root)
                            self.assertEqual(evidence.call_args.args[0], language)
                            self.assertEqual(
                                consume.call_args.kwargs["artifacts"],
                                root / "npm" if language == "typescript" else artifact,
                            )

    def test_python_wheel_consumer_has_no_build_or_registry_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheels = root / "python"
            wheels.mkdir()
            (wheels / "prepared.whl").touch()
            for failure in (False, True):

                def execute(command, **kwargs):
                    if failure:
                        raise subprocess.CalledProcessError(1, "fixture")
                    if "--identity" in command:
                        Path(command[-1]).write_text(
                            json.dumps(
                                {
                                    "python": "3.14.7",
                                    "architecture": "arm64",
                                    "os": "Darwin",
                                }
                            )
                        )

                with (
                    patch("packaged.subprocess.run", side_effect=execute) as run,
                    patch("packaged.record") as evidence,
                ):
                    if failure:
                        with self.assertRaises(subprocess.CalledProcessError):
                            packaged.check("python", root)
                        evidence.assert_not_called()
                    else:
                        packaged.check("python", root)
                        commands = [call.args[0] for call in run.call_args_list]
                        self.assertEqual(len(commands), 4)
                        self.assertIn("--no-index", commands[1])
                        self.assertIn("--no-deps", commands[1])
                        self.assertIn("--no-cache", commands[1])
                        self.assertIn(str(wheels), commands[1])
                        self.assertIn("-I", commands[2])
                        self.assertIn(
                            str(packaged.SDK / "tests/platforms/python_runtime.py"),
                            commands[2],
                        )
                        evidence.assert_called_once()

    def test_installed_python_empty_skipped_and_failed_suites_cannot_pass(self):
        import sys

        for body in (
            "",
            "import unittest\nclass Check(unittest.TestCase):\n @unittest.skip('unavailable')\n def test_api(self): pass\n",
            "import unittest\nclass Check(unittest.TestCase):\n def test_api(self): self.fail('failed')\n",
            "import unittest\nclass Check(unittest.TestCase):\n def test_api(self): pass\n",
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "test_api.py").write_text(body)
                identity = root / "identity.json"
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        str(packaged.SDK / "tests/platforms/python_runtime.py"),
                        str(root),
                        "--identity",
                        str(identity),
                    ],
                    capture_output=True,
                    text=True,
                )
                if body.endswith(" def test_api(self): pass\n") and "skip" not in body:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(json.loads(identity.read_text())["architecture"])
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(identity.exists())

    def test_runtime_architecture_is_not_inferred_from_controller(self):
        with (
            patch("packaged.platform.system", return_value="Darwin"),
            patch("packaged.subprocess.check_output", return_value="1\n"),
        ):
            self.assertEqual(
                packaged.host_runtime("x86_64"), ("macos-x64", "rosetta", "x64")
            )
            self.assertEqual(
                packaged.host_runtime("aarch64"), ("macos-arm64", "native", "arm64")
            )
            with self.assertRaises(ValueError):
                packaged.host_runtime("unlisted")

    def test_android_bundle_is_extracted_for_prepared_consumer(self):
        _, packages, _ = packaged.consumer_tools()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "maven/arboresce-0.0.0-central-bundle.zip"
            bundle.parent.mkdir()
            bundle.touch()
            with (
                patch.object(packages, "extract_zip") as extract,
                patch.object(packages, "validate_maven"),
                patch("packaged.run_suite") as suite,
            ):
                packaged.check("android", root)
            self.assertEqual(extract.call_args.args[0], bundle)
            self.assertEqual(
                suite.call_args.args[1]["repository_directory"],
                extract.call_args.args[1],
            )
            self.assertNotEqual(extract.call_args.args[1], root / "maven")

    def test_linux_artifact_binding_does_not_modify_suite_default(self):
        original = packaged.LinuxPackages.artifacts
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("packaged.run_suite") as suite,
        ):
            root = Path(temporary)
            packaged.check("linux", root)
            self.assertEqual(
                suite.call_args.args, (packaged.LinuxPackages, {"artifacts": root})
            )
        self.assertEqual(packaged.LinuxPackages.artifacts, original)

    def test_unknown_host_is_rejected(self):
        with patch("packaged.platform.system", return_value="Unlisted"):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                packaged.host_runtime("arm64")

    def test_suite_uses_isolated_attributes_and_preserves_original_fixture(self):
        class Fixture(unittest.TestCase):
            value = "original"

            def test_value(self):
                self.assertEqual(self.value, "packaged")

        with contextlib.redirect_stderr(io.StringIO()):
            packaged.run_suite(Fixture, {"value": "packaged"})
        self.assertEqual(Fixture.value, "original")

    def test_failed_skipped_and_empty_suites_cannot_pass(self):
        class Failed(unittest.TestCase):
            def test_failed(self):
                self.fail("fixture failure")

        class Skipped(unittest.TestCase):
            @unittest.skip("fixture missing prerequisite")
            def test_skipped(self):
                pass

        class Empty(unittest.TestCase):
            pass

        for fixture in (Failed, Skipped, Empty):
            with (
                self.subTest(fixture=fixture),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaisesRegex(AssertionError, "Packaged platform"),
            ):
                packaged.run_suite(fixture, {})

    def test_native_empty_skipped_and_failed_suites_emit_no_runtime_evidence(self):
        native_packages, _, _ = packaged.consumer_tools()

        for language in ("c", "cpp"):
            for outcome in ("empty", "skipped", "failed"):
                result = unittest.TestResult()
                if outcome != "empty":
                    result.testsRun = 1
                if outcome == "skipped":
                    result.skipped = [("fixture", "missing prerequisite")]
                if outcome == "failed":
                    result.failures = [("fixture", "failed assertion")]
                with (
                    self.subTest(language=language, outcome=outcome),
                    tempfile.TemporaryDirectory() as temporary,
                    patch.object(native_packages, "extract_native"),
                    patch.object(native_packages, "verify_native_artifacts"),
                    patch("unittest.TextTestRunner.run", return_value=result),
                    patch("packaged.record") as evidence,
                    patch("packaged.platform.platform", return_value="Synthetic host"),
                ):
                    with self.assertRaisesRegex(AssertionError, "Installed native"):
                        packaged.check(language, Path(temporary))
                    evidence.assert_not_called()
