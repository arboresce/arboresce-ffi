import hashlib
import importlib.util
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import unittest
import urllib.request
from pathlib import Path

from runtime_evidence import architecture as normalized_architecture
from runtime_evidence import container_runtime, record

SDK = Path(__file__).resolve().parents[2]
VERSION = tomllib.loads((SDK / "Cargo.toml").read_text())["workspace"]["package"][
    "version"
]
spec = importlib.util.spec_from_file_location(
    "sdk_packages", SDK / "tests/consumers/package_tools.py"
)
packages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packages)


class LinuxPackages(unittest.TestCase):
    artifacts = Path(
        os.environ.get("ARBORESCE_PACKAGE_ROOT", SDK / "build/dist")
    ).resolve()

    def run_command(self, command, cwd=None):
        result = subprocess.run(
            [str(item) for item in command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    @unittest.skipUnless(
        platform.system() == "Darwin", "The macOS x64 consumer requires macOS"
    )
    def test_macos_x64_npm_consumer(self):
        tools = SDK / "build/node-x64"
        node = tools / "node-v22.22.3-darwin-x64/bin/node"
        if not node.is_file():
            tools.mkdir(parents=True, exist_ok=True)
            name = "node-v22.22.3-darwin-x64.tar.gz"
            base = "https://nodejs.org/dist/v22.22.3/"
            checksums = (
                urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60)
                .read()
                .decode()
            )
            expected = next(
                line.split()[0]
                for line in checksums.splitlines()
                if line.endswith("  " + name)
            )
            artifact = tools / name
            urllib.request.urlretrieve(base + name, artifact)
            self.assertEqual(
                hashlib.sha256(artifact.read_bytes()).hexdigest(), expected
            )
            with tarfile.open(artifact) as archive:
                archive.extractall(tools, filter="data")
        with tempfile.TemporaryDirectory(prefix="arboresce-node-x64-") as temporary:
            root = Path(temporary)
            npm = tools / "node-v22.22.3-darwin-x64/lib/node_modules/npm/bin/npm-cli.js"
            self.run_command(
                [
                    node,
                    npm,
                    "install",
                    "--ignore-scripts",
                    "--offline",
                    "--no-audit",
                    "--no-fund",
                    self.artifacts / f"npm/arboresce-native-darwin-x64-{VERSION}.tgz",
                    self.artifacts / f"npm/arboresce-{VERSION}.tgz",
                ],
                cwd=root,
            )
            shutil.copyfile(
                SDK / "tests/platforms/fixtures/node/consumer.mjs",
                root / "consumer.mjs",
            )
            result = self.run_command([node, "consumer.mjs"], cwd=root)
            self.assertEqual(result.stdout, "Arboresce\n")
            record(
                "typescript",
                "macos-x64",
                "native" if normalized_architecture() == "x64" else "rosetta",
                {
                    "node": self.run_command([node, "--version"]).stdout.strip(),
                    "os": platform.platform(),
                },
                cpu="x64",
            )

    def test_linux_packaged_consumers(self):
        with tempfile.TemporaryDirectory(
            prefix="arboresce-linux-packages-"
        ) as temporary:
            root = Path(temporary)
            for language in ("npm", "python"):
                shutil.copytree(self.artifacts / language, root / "dist" / language)
            bundle = self.artifacts / f"maven/arboresce-{VERSION}-central-bundle.zip"
            if bundle.is_file():
                packages.extract_zip(bundle, root / "maven")
            else:
                shutil.copytree(self.artifacts / "maven", root / "maven")
            packages.validate_maven(sdk=SDK, artifacts=root / "maven")
            consumer = root / "runtime-consumer"
            shutil.copytree(SDK / "tests/consumers/kotlin", consumer)
            self.run_command(
                [
                    SDK / "bindings/kotlin/gradlew",
                    "--no-daemon",
                    "copyRuntimeDependencies",
                ],
                cwd=consumer,
            )
            shutil.copytree(consumer / "build/runtime", root / "runtime")
            shutil.copytree(SDK / "tests/platforms/fixtures", root / "fixtures")
            shutil.copytree(SDK / "bindings/python/tests", root / "python-tests")
            shutil.copyfile(
                SDK / "tests/platforms/python_runtime.py", root / "python_runtime.py"
            )
            self.run_command(
                ["npm", "run", "test:compile", "--prefix", SDK / "bindings/typescript"]
            )
            shutil.copytree(SDK / "bindings/typescript/build/test", root / "node-tests")
            jar = f"/artifacts/maven/ai/arboresce/arboresce/{VERSION}/arboresce-{VERSION}.jar"
            for architecture, suffix in (("arm64", "arm64"), ("amd64", "x64")):
                with self.subTest(architecture=architecture):
                    base = [
                        "docker",
                        "run",
                        "--rm",
                        "--platform",
                        f"linux/{architecture}",
                        "--mount",
                        f"type=bind,src={root},dst=/artifacts,readonly",
                        "--workdir",
                        "/tmp",
                    ]
                    native = f"/artifacts/dist/npm/arboresce-native-linux-{suffix}-gnu-{VERSION}.tgz"
                    node = f"mkdir consumer && cd consumer && cp /artifacts/fixtures/node/package.json . && npm install --offline --ignore-scripts --no-audit --no-fund {native} /artifacts/dist/npm/arboresce-{VERSION}.tgz >/dev/null && cp -R /artifacts/node-tests test && node --test test/node.test.js test/wasm.test.js"
                    self.run_command(
                        base + ["node:22.22.3-bookworm-slim", "sh", "-ec", node]
                    )
                    print(
                        f"PASS: Installed Node/WASM public regression suite on Linux {architecture}"
                    )
                    mode, runtime = container_runtime(
                        "node:22.22.3-bookworm-slim", architecture
                    )
                    runtime["node"] = self.run_command(
                        base + ["node:22.22.3-bookworm-slim", "node", "--version"]
                    ).stdout.strip()
                    record(
                        "typescript", f"linux-{suffix}", mode, runtime, cpu=architecture
                    )
                    for java_version in (8, 21):
                        with self.subTest(java=java_version):
                            code = f'java -version >&2 && cp /artifacts/fixtures/jvm/Consumer.java . && javac -cp {jar} Consumer.java && java -Djna.nosys=true -cp ".:{jar}:/artifacts/runtime/*" Consumer'
                            result = self.run_command(
                                base
                                + [
                                    f"eclipse-temurin:{java_version}-jdk-jammy",
                                    "sh",
                                    "-ec",
                                    code,
                                ]
                            )
                            self.assertEqual(result.stdout, "Arboresce\n")
                            self.assertIn(
                                'version "1.8.'
                                if java_version == 8
                                else 'version "21.',
                                result.stderr,
                            )
                            print(
                                f"PASS: Installed JVM consumer on Java {java_version}, Linux {architecture}"
                            )
                            mode, runtime = container_runtime(
                                f"eclipse-temurin:{java_version}-jdk-jammy",
                                architecture,
                            )
                            runtime["java"] = result.stderr.strip()
                            record(
                                "kotlin",
                                f"linux-{suffix}",
                                mode,
                                runtime,
                                cpu=architecture,
                            )
                    code = f"python -m pip install --quiet --no-index --find-links /artifacts/dist/python arboresce=={VERSION} && python -I /artifacts/python_runtime.py /artifacts/python-tests"
                    self.run_command(
                        base + ["python:3.14.7-slim-bookworm", "sh", "-ec", code]
                    )
                    print(
                        f"PASS: Installed Python public regression suite on Linux {architecture}"
                    )
                    mode, runtime = container_runtime(
                        "python:3.14.7-slim-bookworm", architecture
                    )
                    runtime["python"] = self.run_command(
                        base + ["python:3.14.7-slim-bookworm", "python", "--version"]
                    ).stdout.strip()
                    record("python", f"linux-{suffix}", mode, runtime, cpu=architecture)


if __name__ == "__main__":
    unittest.main()
