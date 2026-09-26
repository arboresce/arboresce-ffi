import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SDK = Path(__file__).resolve().parents[2]


class NativeCommands:
    package = SDK / "build/native/install"
    native_build = SDK / "build/native"
    fixtures = SDK / "bindings"

    def run_command(self, command, cwd=None, env=None):
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, timeout=240
        )
        self.assertEqual(
            result.returncode, 0, result.stdout.decode() + result.stderr.decode()
        )
        return result

    def exact_print(self, executable, env=None):
        result = self.run_command([str(executable)], env=env)
        self.assertEqual(result.stdout, b"Arboresce\n")
        self.assertEqual(result.stderr, b"")

    def cmake_consumer(self, root, prefix, language, linkage, no_exceptions=False):
        source = root / f"{language}-fixture"
        if not source.exists():
            shutil.copytree(self.fixtures / language / "tests/consumer", source)
        build = root / f"{language}-{linkage}-{prefix.name}-{no_exceptions}"
        environment = dict(os.environ)
        environment.pop("CMAKE_PREFIX_PATH", None)
        environment.pop("CMAKE_TOOLCHAIN_FILE", None)
        environment.pop("CPATH", None)
        environment.pop("LIBRARY_PATH", None)
        environment["CXX"] = (
            "/nonexistent-cxx" if language == "c" else shutil.which("c++")
        )
        guards = root / "unavailable-build-tools"
        guards.mkdir(exist_ok=True)
        forbidden = ["rustc", "cargo", "cbindgen"]
        if language == "c":
            forbidden.extend(["c++", "g++", "clang++"])
        for tool in forbidden:
            guard = guards / tool
            shutil.copyfile(self.fixtures / "c/tests/tool-unavailable.sh", guard)
            guard.chmod(0o755)
        environment["PATH"] = str(guards) + os.pathsep + environment["PATH"]
        self.run_command(
            [
                shutil.which("cmake"),
                "-S",
                str(source),
                "-B",
                str(build),
                f"-DCMAKE_PREFIX_PATH={prefix}",
                f"-DARBORESCE_LINKAGE={linkage}",
                f"-DARBORESCE_NO_EXCEPTIONS={'ON' if no_exceptions else 'OFF'}",
                "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF",
                "-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF",
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            ],
            env=environment,
        )
        self.run_command(
            [shutil.which("cmake"), "--build", str(build)], env=environment
        )
        commands = (build / "compile_commands.json").read_text()
        self.assertNotIn(str(SDK), commands)
        if language == "c":
            self.assertNotIn(
                "CMAKE_CXX_COMPILER:", (build / "CMakeCache.txt").read_text()
            )
        self.exact_print(build / "consumer", environment)

    def relocated_consumers(self, language, no_exceptions=False):
        self.assertTrue(
            self.package.is_dir(), "Run make install-c or make build-cpp first"
        )
        with tempfile.TemporaryDirectory(
            prefix="arboresce-native-consumer-"
        ) as temporary:
            root = Path(temporary)
            original = root / "original"
            shutil.copytree(self.package, original, symlinks=True)
            for linkage in ("static", "shared"):
                self.cmake_consumer(root, original, language, linkage, no_exceptions)
            relocated = root / "relocated prefix"
            original.rename(relocated)
            for linkage in ("static", "shared"):
                self.cmake_consumer(root, relocated, language, linkage, no_exceptions)


class NativeAbi(NativeCommands, unittest.TestCase):
    def test_layout_and_exact_print(self):
        baseline = json.loads((self.fixtures / "c/tests/abi_v1.json").read_text())
        for linkage in ("static", "shared"):
            result = self.run_command(
                [str(self.native_build / "c" / f"c_layout_{linkage}")]
            )
            actual = json.loads(result.stdout)
            self.assertEqual(actual, baseline["layouts"][str(actual["pointer_bits"])])
            self.exact_print(self.native_build / "c" / f"c_print_name_{linkage}")

    def test_symbols_and_loader_identity(self):
        baseline = json.loads((self.fixtures / "c/tests/abi_v1.json").read_text())
        stage = self.native_build / "stage"
        if platform.system() == "Darwin":
            library = stage / "libarboresce_c.1.dylib"
            symbols = self.run_command(["nm", "-gU", str(library)]).stdout.decode()
            actual = sorted(
                line.split()[-1].removeprefix("_")
                for line in symbols.splitlines()
                if line.strip()
            )
            identity = (
                self.run_command(["otool", "-D", str(library)])
                .stdout.decode()
                .splitlines()[1:]
            )
            self.assertEqual(identity, ["@rpath/libarboresce_c.1.dylib"])
            metadata = self.run_command(["otool", "-l", str(library)]).stdout.decode()
            self.assertNotIn("LC_RPATH", metadata)
        else:
            library = stage / "libarboresce_c.so.1"
            symbols = self.run_command(
                ["nm", "-D", "--defined-only", str(library)]
            ).stdout.decode()
            actual = sorted(
                line.split()[-1] for line in symbols.splitlines() if line.strip()
            )
            metadata = self.run_command(["readelf", "-d", str(library)]).stdout.decode()
            self.assertIn("[libarboresce_c.so.1]", metadata)
            self.assertNotIn("RPATH", metadata)
            self.assertNotIn("RUNPATH", metadata)
        self.assertEqual(actual, baseline["symbols"])
        evidence = {
            "scope": "C host ABI symbols and loader identity",
            "execution": "native",
            "host": platform.platform(),
            "architecture": platform.machine(),
            "rust": self.run_command(["rustc", "-vV"]).stdout.decode().strip(),
            "c_compiler": self.run_command(["cc", "--version"]).stdout.decode().strip(),
            "cmake": self.run_command(["cmake", "--version"])
            .stdout.decode()
            .splitlines()[0],
            "abi_version": baseline["abi_version"],
            "symbols": actual,
            "native_static_libraries": (stage / "native-static-libs.txt")
            .read_text()
            .strip(),
            "shared_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            "loader_metadata": metadata,
            "cpu_policy": "Rust target default; position independent code; no target-cpu=native",
        }
        (self.native_build / "abi-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )


class CConsumers(NativeCommands, unittest.TestCase):
    def test_installed_abi_null_layout_and_concurrent_calls(self):
        baseline = json.loads((self.fixtures / "c/tests/abi_v1.json").read_text())
        with tempfile.TemporaryDirectory(
            prefix="arboresce-installed-abi-"
        ) as temporary:
            root = Path(temporary)
            prefix = root / "installed"
            shutil.copytree(self.package, prefix, symlinks=True)
            environment = dict(
                os.environ,
                PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"),
                PKG_CONFIG_PATH="",
            )
            for linkage in ("shared", "static"):
                command = ["pkg-config", "--cflags", "--libs"]
                if linkage == "static":
                    command.append("--static")
                flags = shlex.split(
                    self.run_command(
                        command + ["arboresce"], env=environment
                    ).stdout.decode()
                )
                if linkage == "static":
                    flags = [
                        str(prefix / "lib/libarboresce_c.a")
                        if flag == "-larboresce_c"
                        else flag
                        for flag in flags
                    ]
                for fixture in ("api", "layout", "print_name"):
                    source = root / f"{fixture}.c"
                    shutil.copyfile(self.fixtures / f"c/tests/{fixture}.c", source)
                    executable = root / f"{fixture}-{linkage}"
                    self.run_command(
                        [
                            "cc",
                            "-std=c11",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            "-UNDEBUG",
                            "-pthread",
                            str(source),
                            *flags,
                            f"-Wl,-rpath,{prefix / 'lib'}",
                            "-o",
                            str(executable),
                        ]
                    )
                    result = self.run_command([str(executable)])
                    self.assertEqual(result.stderr, b"")
                    if fixture == "layout":
                        layout = json.loads(result.stdout)
                        self.assertEqual(
                            layout, baseline["layouts"][str(layout["pointer_bits"])]
                        )
                    else:
                        self.assertEqual(
                            result.stdout,
                            b"Arboresce\n" if fixture == "print_name" else b"",
                        )

    def test_cmake_static_shared_and_relocation(self):
        self.relocated_consumers("c")

    def test_installed_metadata_has_no_build_paths(self):
        for file in self.package.rglob("*"):
            if file.suffix in (".cmake", ".pc", ".h", ".hpp"):
                content = file.read_text()
                self.assertNotIn(str(SDK), content, str(file))
                self.assertNotIn(str(SDK.parent), content, str(file))
                self.assertNotIn("/Volumes/", content, str(file))

    def test_pkg_config_static_shared_and_sanitized_c(self):
        with tempfile.TemporaryDirectory(prefix="arboresce-pkg-config-") as temporary:
            root = Path(temporary)
            prefix = root / "relocated"
            shutil.copytree(self.package, prefix, symlinks=True)
            source = root / "consumer.c"
            shutil.copyfile(self.fixtures / "c/tests/consumer/main.c", source)
            environment = dict(
                os.environ,
                PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"),
                PKG_CONFIG_PATH="",
            )
            for linkage in ("shared", "static"):
                command = ["pkg-config", "--cflags", "--libs"]
                if linkage == "static":
                    command.append("--static")
                flags = shlex.split(
                    self.run_command(
                        command + ["arboresce"], env=environment
                    ).stdout.decode()
                )
                if linkage == "static":
                    flags = [
                        str(prefix / "lib/libarboresce_c.a")
                        if flag == "-larboresce_c"
                        else flag
                        for flag in flags
                    ]
                executable = root / linkage
                self.run_command(
                    [
                        "cc",
                        "-std=c11",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        str(source),
                        *flags,
                        f"-Wl,-rpath,{prefix / 'lib'}",
                        "-o",
                        str(executable),
                    ]
                )
                self.exact_print(executable)
                instrumented = root / f"{linkage}-c-only-asan-ubsan"
                self.run_command(
                    [
                        "cc",
                        "-std=c11",
                        "-fsanitize=address,undefined",
                        str(source),
                        *flags,
                        f"-Wl,-rpath,{prefix / 'lib'}",
                        "-o",
                        str(instrumented),
                    ]
                )
                self.exact_print(instrumented)


class CppConsumers(NativeCommands, unittest.TestCase):
    def test_cmake_static_shared_and_relocation(self):
        self.relocated_consumers("cpp")

    def test_no_exceptions_static_shared_and_relocation(self):
        self.relocated_consumers("cpp", no_exceptions=True)
