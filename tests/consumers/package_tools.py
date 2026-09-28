import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SDK = Path(__file__).resolve().parents[2]
NATIVE_NPM_LICENSES = {"LICENSE-MIT": "LICENSE.MIT", "LICENSE-APACHE": "LICENSE.APACHE"}


def run(command, cwd=None, env=None, capture=False, check=True):
    return subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        env=os.environ | (env or {}),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=check,
    )


def version(sdk=SDK):
    return tomllib.loads((sdk / "Cargo.toml").read_text())["workspace"]["package"][
        "version"
    ]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, name):
    path = root / name
    if (
        Path(name).is_absolute()
        or ".." in Path(name).parts
        or not path.is_file()
        or path.resolve() != path.absolute()
    ):
        raise ValueError(f"Invalid or missing Go distribution file: {name}")
    return path


def distribution_files(sdk, module=None):
    sdk = Path(sdk).resolve()
    module = Path(module) if module is not None else sdk / "bindings/go"
    policy = json.loads((module / "native-platforms.json").read_text())
    if policy != json.loads((sdk / "bindings/go/native-platforms.json").read_text()):
        raise ValueError("Go package platform policy differs from the SDK contract")
    generator = json.loads((sdk / "crates/ffi/go-bindgen.json").read_text())
    cargo = tomllib.loads((sdk / "Cargo.toml").read_text())
    compiler = tomllib.loads((sdk / "rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    core = cargo["workspace"]["dependencies"]["arboresce"]["rev"]
    inputs = [
        {"path": name, "sha256": digest(safe_file(sdk, name))}
        for name in policy["source_files"]
    ]
    files = {name: safe_file(module, name) for name in policy["package_files"]}
    identities = set()
    for target_platform, target in policy["platforms"].items():
        name = f"internal/native/lib/{target_platform}/libarboresce_ffi.a"
        archive = safe_file(module, name)
        receipt = safe_file(module, name + ".json")
        data = json.loads(receipt.read_text())
        expected = dict(
            schema=1,
            platform=target_platform,
            rust_target=target,
            profile="release",
            core_rev=core,
            archive_sha256=digest(archive),
            inputs=inputs,
        )
        if any(data.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Stale or corrupt Go native artifact: {target_platform}")
        identity = data.get("generator", {})
        if any(
            identity.get(key) != value for key, value in generator.items()
        ) or not re.fullmatch(r"[0-9a-f]{64}", identity.get("binary_sha256", "")):
            raise ValueError(f"Wrong Go generator provenance: {target_platform}")
        if not data.get("rustc", "").startswith(f"rustc {compiler} "):
            raise ValueError(f"Wrong Rust toolchain: {target_platform}")
        identities.add(identity["binary_sha256"])
        files[name], files[name + ".json"] = archive, receipt
    if len(identities) != 1:
        raise ValueError("Go artifacts have inconsistent generator binaries")
    return files


def write_zip(files, destination, prefix):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        output = Path(temporary) / "package.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in sorted(files.items()):
                entry = zipfile.ZipInfo(
                    f"{prefix}/{name}", date_time=(1980, 1, 1, 0, 0, 0)
                )
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, source.read_bytes())
        output.replace(destination)


def package_go(sdk, destination, prefix):
    write_zip(distribution_files(sdk), destination, prefix)


def write_go_proxy(files, root, release, timestamp="2026-01-01T00:00:00Z"):
    proxy = root / "github.com/arboresce/arboresce-ffi/bindings/go/@v"
    proxy.mkdir(parents=True, exist_ok=True)
    write_zip(
        files,
        proxy / f"v{release}.zip",
        f"github.com/arboresce/arboresce-ffi/bindings/go@v{release}",
    )
    shutil.copyfile(files["go.mod"], proxy / f"v{release}.mod")
    (proxy / f"v{release}.info").write_text(
        json.dumps({"Version": f"v{release}", "Time": timestamp}) + "\n"
    )
    (proxy / "list").write_text(f"v{release}\n")


def extract_zip(source, destination):
    with zipfile.ZipFile(source) as archive:
        for entry in archive.infolist():
            path = Path(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError(f"Unsafe package member: {entry.filename}")
        archive.extractall(destination)


def build_go_distribution(sdk=SDK):
    files = distribution_files(sdk)
    release = version(sdk)
    destination = sdk / "build/dist/go"
    write_zip(
        files, destination / f"arboresce-go-{release}.zip", f"arboresce-go-{release}"
    )
    write_go_proxy(files, destination / "proxy", release)
    print(f"Prepared Go ZIP and file proxy: {destination}")


def test_go_consumer(sdk=SDK, artifacts=None):
    packages = Path(artifacts) if artifacts is not None else sdk / "build/dist/go"
    with tempfile.TemporaryDirectory(prefix="arboresce-go-consumer-") as temporary:
        root = Path(temporary)
        consumer = root / "consumer"
        shutil.copytree(sdk / "tests/consumers/go", consumer)
        (consumer / "api_test.go").write_text(
            (sdk / "bindings/go/api_test.go")
            .read_text()
            .replace("package arboresce_test", "package consumer_test", 1)
        )
        shutil.copytree(sdk / "bindings/go/testdata", consumer / "testdata")
        extract_zip(packages / f"arboresce-go-{version(sdk)}.zip", root / "unpacked")
        files = distribution_files(
            sdk, root / "unpacked" / f"arboresce-go-{version(sdk)}"
        )
        write_go_proxy(files, root / "proxy", version(sdk))
        env = {
            "GOWORK": "off",
            "GOPROXY": (root / "proxy").as_uri(),
            "GOSUMDB": "off",
            "GONOPROXY": "",
            "GOPRIVATE": "",
            "GOMODCACHE": str(root / "cache"),
        }
        run(
            ["go", "mod", "download", "github.com/arboresce/arboresce-ffi/bindings/go"],
            cwd=consumer,
            env=env,
        )
        run(["go", "test", "-race", "-count=1", "-v", "./..."], cwd=consumer, env=env)
    run(
        [
            "uv",
            "run",
            "--python",
            "3.14.7",
            "--no-project",
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/consumers",
            "-p",
            "test_packages.py",
            "-v",
        ],
        cwd=sdk,
    )


def native_npm_suffix():
    host = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(
        platform.machine()
    )
    if not host or not arch:
        raise ValueError("No declared native npm package for this host")
    return f"{host}-{arch}" + ("-gnu" if host == "linux" else "")


def pack_npm(source, destination, licenses=("LICENSE-MIT", "LICENSE-APACHE")):
    result = subprocess.run(
        [
            "npm",
            "pack",
            "--ignore-scripts",
            "--json",
            "--pack-destination",
            str(destination),
        ],
        cwd=source,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    metadata = json.loads(result.stdout)
    if len(metadata) != 1:
        raise ValueError("Expected one npm package")
    artifact = destination / metadata[0]["filename"]
    with tarfile.open(artifact) as archive:
        names = {item.name for item in archive.getmembers()}
        if not {
            "package/package.json",
            *(f"package/{name}" for name in licenses),
        }.issubset(names):
            raise ValueError(f"Incomplete npm license inventory: {artifact.name}")
        if any(
            part in {"test", "tests", "node_modules"}
            for name in names
            for part in Path(name).parts
        ):
            raise ValueError(
                f"Test or dependency files in npm package: {artifact.name}"
            )
    print(f"Prepared {artifact}")
    return artifact


def validate_native_npm_manifest(manifest, item, target, metadata):
    expected = {
        "name": item["name"],
        "version": metadata["optionalDependencies"][item["name"]],
        "main": item["binary"],
        "files": [item["binary"]],
        "os": [target["os"]],
        "cpu": [target["cpu"]],
        "engines": metadata["engines"],
        "license": metadata["license"],
        "libc": [target["libc"]] if target.get("libc") else None,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Native npm metadata differs: {item['name']}/{key}")


def prepare_native_npm(sdk=SDK):
    source = sdk / "bindings/typescript"
    metadata = json.loads((source / "package.json").read_text())
    specification = importlib.util.spec_from_file_location(
        "arboresce_npm_targets", sdk / "tests/platforms/targets.py"
    )
    targets = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(targets)
    policy = targets.load(sdk)
    installed = source / "node_modules/@napi-rs/cli"
    if (
        json.loads((installed / "package.json").read_text())["version"]
        != metadata["devDependencies"]["@napi-rs/cli"]
    ):
        raise ValueError("Node generator version differs; run make setup-typescript")
    staging = sdk / "build/typescript"
    staging.mkdir(parents=True, exist_ok=True)
    npm = staging / "npm"
    if npm.exists():
        shutil.rmtree(npm)
    shutil.copyfile(source / "package.json", staging / "package.json")
    run(
        ["node", installed / "dist/cli.js", "create-npm-dirs", "--npm-dir", "npm"],
        cwd=staging,
    )
    packages = {}
    for target, item in policy["node_packages"].items():
        suffix = item["name"].removeprefix(metadata["napi"]["packageName"] + "-")
        if suffix == item["name"] or "/" in suffix or suffix in {"", ".", ".."}:
            raise ValueError("Native npm package prefix differs from target policy")
        directory = npm / suffix
        manifest = json.loads((directory / "package.json").read_text())
        validate_native_npm_manifest(
            manifest, item, policy["platforms"][target], metadata
        )
        for filename, packaged_name in NATIVE_NPM_LICENSES.items():
            shutil.copyfile(source / filename, directory / packaged_name)
        packages[item["name"]] = directory
    if set(npm.iterdir()) != set(packages.values()):
        raise ValueError("Generated npm directory inventory differs from target policy")
    return packages


def validate_native_npm_archive(artifact, directory, source):
    manifest = json.loads((directory / "package.json").read_text())
    expected = {
        "package.json",
        "README.md",
        *NATIVE_NPM_LICENSES.values(),
        manifest["main"],
    }
    with tarfile.open(artifact) as archive:
        if {item.name for item in archive.getmembers()} != {
            f"package/{name}" for name in expected
        }:
            raise ValueError("Native npm archive inventory differs")
        for name in expected:
            original = (
                source / "native" / name
                if name == manifest["main"]
                else directory / name
            )
            if archive.extractfile(f"package/{name}").read() != original.read_bytes():
                raise ValueError(f"Native npm archive contents differ: {name}")


def package_typescript(sdk=SDK):
    source = sdk / "bindings/typescript"
    native_packages = prepare_native_npm(sdk)
    destination = sdk / "build/dist/npm"
    with tempfile.TemporaryDirectory(prefix="arboresce-npm-pack-") as temporary:
        staging = Path(temporary)
        packages = staging / "packages"
        packages.mkdir()
        host_package = f"@arboresce/native-{native_npm_suffix()}"
        found_host = False
        for name, native in sorted(native_packages.items()):
            manifest = json.loads((native / "package.json").read_text())
            binary = source / "native" / manifest["main"]
            if not binary.is_file():
                if name == host_package:
                    raise ValueError(f"Missing npm native artifact: {binary.name}")
                continue
            shutil.copyfile(binary, native / binary.name)
            artifact = pack_npm(native, packages, NATIVE_NPM_LICENSES.values())
            validate_native_npm_archive(artifact, native, source)
            found_host |= name == host_package
        if not found_host:
            raise ValueError(f"Host native package is undeclared: {host_package}")
        artifact = pack_npm(source, packages)
        with tarfile.open(artifact) as archive:
            names = {item.name for item in archive.getmembers()}
            required = {
                f"package/{name}"
                for name in (
                    "dist/index.js",
                    "dist/index.d.ts",
                    "dist/browser.js",
                    "dist/browser.d.ts",
                    "native/native.cjs",
                    "wasm/arboresce_wasm_bg.wasm",
                )
            }
            if not required.issubset(names) or any(
                name.endswith(".node") for name in names
            ):
                raise ValueError(
                    "npm facade must include declarations/WASM and use separate native packages"
                )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(packages, destination)


def test_typescript_consumer(browser=False, sdk=SDK, artifacts=None):
    release = version(sdk)
    packages = Path(artifacts) if artifacts is not None else sdk / "build/dist/npm"
    main = packages / f"arboresce-{release}.tgz"
    native = packages / f"arboresce-native-{native_npm_suffix()}-{release}.tgz"
    with tempfile.TemporaryDirectory(prefix="arboresce-npm-consumer-") as temporary:
        root = Path(temporary)
        consumer = root / "consumer"
        shutil.copytree(sdk / "tests/consumers/typescript", consumer)
        shutil.copytree(sdk / "bindings/typescript/test", consumer / "test")
        run(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=consumer,
        )
        run(
            [
                "npm",
                "install",
                "--offline",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                main,
                native,
            ],
            cwd=consumer,
        )
        run(["npm", "test"], cwd=consumer)
        invalid = run(
            [
                "node",
                "node_modules/typescript/bin/tsc",
                "--strict",
                "--noEmit",
                "--module",
                "NodeNext",
                "--target",
                "ES2022",
                "test/types/invalid.ts",
            ],
            cwd=consumer,
            capture=True,
            check=False,
        )
        if (
            invalid.returncode == 0
            or "TS2322" not in invalid.stdout
            or invalid.stdout.count("error TS") != 1
        ):
            raise ValueError(
                f"TypeScript negative consumer must fail only on the incorrect return type:\n{invalid.stdout}"
            )
        print("PASS: Installed TypeScript declarations reject incorrect consumer types")
        run(["node", "unsupported-platform.mjs"], cwd=consumer)
        if browser:
            run(["node", "--test", "test/browser/chromium.test.mjs"], cwd=consumer)
        missing = root / "missing"
        missing.mkdir()
        (missing / "package.json").write_text(
            json.dumps({"private": True, "type": "module"})
        )
        shutil.copyfile(consumer / "missing-native.mjs", missing / "missing-native.mjs")
        run(
            [
                "npm",
                "install",
                "--offline",
                "--ignore-scripts",
                "--omit=optional",
                "--no-audit",
                "--no-fund",
                main,
            ],
            cwd=missing,
        )
        run(["node", "missing-native.mjs"], cwd=missing)


def pom_dependencies(path):
    root = ET.parse(path).getroot()
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    return {
        (
            item.findtext("m:groupId", namespaces=namespace),
            item.findtext("m:artifactId", namespaces=namespace),
        ): item
        for item in root.findall("m:dependencies/m:dependency", namespace)
    }, namespace


def validate_maven(android=False, sdk=SDK, artifacts=None):
    release = version(sdk)
    artifact = "arboresce-android" if android else "arboresce"
    repository = Path(artifacts) if artifacts is not None else sdk / "build/dist/maven"
    base = repository / f"ai/arboresce/{artifact}/{release}"
    prefix = f"{artifact}-{release}"
    dependencies, namespace = pom_dependencies(base / f"{prefix}.pom")
    jna = dependencies.get(("net.java.dev.jna", "jna"))
    if (
        jna is None
        or jna.findtext("m:version", namespaces=namespace) != "5.17.0"
        or jna.findtext("m:scope", namespaces=namespace) != "runtime"
    ):
        raise ValueError("JNA must be an exact runtime dependency in the installed POM")
    if android:
        facade = dependencies.get(("ai.arboresce", "arboresce"))
        if (
            facade is None
            or facade.findtext("m:version", namespaces=namespace) != release
        ):
            raise ValueError(
                "Android POM must depend on the matching public JVM artifact"
            )
        exclusions = facade.findall("m:exclusions/m:exclusion", namespace)
        if not any(
            item.findtext("m:groupId", namespaces=namespace) == "net.java.dev.jna"
            and item.findtext("m:artifactId", namespaces=namespace) == "jna"
            for item in exclusions
        ):
            raise ValueError("Android POM must exclude desktop JNA")
        if jna.findtext("m:type", namespaces=namespace) != "aar":
            raise ValueError("Android POM must use the JNA AAR")
    for classifier in ("sources", "javadoc"):
        with zipfile.ZipFile(base / f"{prefix}-{classifier}.jar") as archive:
            names = set(archive.namelist())
            if not {"META-INF/LICENSE-MIT", "META-INF/LICENSE-APACHE"}.issubset(names):
                raise ValueError(f"Missing {classifier} licenses")
            if classifier == "javadoc" and not any(
                name.endswith(".html") for name in names
            ):
                raise ValueError("API documentation archive is empty")
            if classifier == "sources" and not any(
                name.endswith(".kt" if not android else "AndroidManifest.xml")
                for name in names
            ):
                raise ValueError("Source archive is empty")
    with zipfile.ZipFile(base / f"{prefix}.{'aar' if android else 'jar'}") as archive:
        names = set(archive.namelist())
        if any("consumer/" in name or name.endswith("Test.class") for name in names):
            raise ValueError("Consumer test helpers leaked into the JVM package")
        if not android and not {
            "META-INF/LICENSE-MIT",
            "META-INF/LICENSE-APACHE",
            "ai/arboresce/Arboresce.class",
        }.issubset(names):
            raise ValueError("Missing JVM facade or licenses")
        if android and not {
            "AndroidManifest.xml",
            "classes.jar",
            "META-INF/LICENSE-MIT",
            "META-INF/LICENSE-APACHE",
        }.issubset(names):
            raise ValueError("Incomplete Android AAR or license inventory")
    print(f"PASS: Unsigned local Maven metadata and artifact inventories: {artifact}")


def java8_executable():
    if os.environ.get("JAVA8_HOME"):
        executable = Path(os.environ["JAVA8_HOME"]) / "bin/java"
        if not executable.is_file():
            raise ValueError("JAVA8_HOME does not contain bin/java")
        identity = run([executable, "-version"], capture=True)
        if 'version "1.8.' not in identity.stdout:
            raise ValueError("JAVA8_HOME must select Java 8")
        return executable
    if platform.system() == "Darwin":
        result = run(["/usr/libexec/java_home", "-v", "1.8"], capture=True, check=False)
        if result.returncode == 0:
            executable = Path(result.stdout.strip()) / "bin/java"
            identity = run([executable, "-version"], capture=True)
            if 'version "1.8.' in identity.stdout:
                return executable
    for root in (Path("/usr/lib/jvm"), Path("/opt/java")):
        if root.is_dir():
            for executable in sorted(root.glob("*/bin/java")):
                result = run([executable, "-version"], capture=True, check=False)
                if result.returncode == 0 and 'version "1.8.' in result.stdout:
                    return executable
    return None


def wrong_architecture(data):
    changed = bytearray(data)
    if data[:4] == b"\xcf\xfa\xed\xfe":
        machine = struct.unpack_from("<I", data, 4)[0]
        struct.pack_into(
            "<I", changed, 4, 0x01000007 if machine == 0x0100000C else 0x0100000C
        )
    elif data[:4] == b"\x7fELF":
        endian = "<" if data[5] == 1 else ">"
        machine = struct.unpack_from(endian + "H", data, 18)[0]
        struct.pack_into(endian + "H", changed, 18, 62 if machine == 183 else 183)
    else:
        raise ValueError("Unsupported native format in JVM loading fixture")
    return bytes(changed)


def test_jvm_loading(consumer, sdk):
    output = consumer / "java8-classes"
    run(
        ["javac", "--release", "8", "-d", output, consumer / "Loading.java"],
        cwd=consumer,
    )
    deployment = consumer / "read only deployment with spaces"
    shutil.copytree(consumer / "build/runtime", deployment)
    extraction = consumer / "writable extraction with spaces"
    extraction.mkdir()
    command = [
        "java",
        "-Djna.nosys=true",
        f"-Djna.tmpdir={extraction}",
        f"-Djava.io.tmpdir={extraction}",
        "-cp",
        output,
        "Loading",
    ]
    for path in deployment.iterdir():
        path.chmod(0o444)
    deployment.chmod(0o555)
    try:
        run(command + [deployment], cwd=consumer)
    finally:
        deployment.chmod(0o755)
    print(
        "PASS: Two independent JVM classloaders and read-only deployment extract through a writable cache"
    )
    for kind in ("missing", "wrong-architecture"):
        target = consumer / kind
        shutil.copytree(consumer / "build/runtime", target)
        jar = target / f"arboresce-{version(sdk)}.jar"
        altered = target / "altered.jar"
        with (
            zipfile.ZipFile(jar) as source,
            zipfile.ZipFile(altered, "w") as destination,
        ):
            for entry in source.infolist():
                content = source.read(entry)
                if entry.filename.endswith((".so", ".dylib")):
                    if kind == "missing":
                        continue
                    content = wrong_architecture(content)
                destination.writestr(entry, content)
        altered.replace(jar)
        result = run(
            command + [target],
            cwd=consumer,
            capture=True,
            check=False,
            env={"LD_LIBRARY_PATH": "", "DYLD_LIBRARY_PATH": ""},
        )
        if (
            result.returncode == 0
            or "UnsatisfiedLinkError" not in result.stdout
            or "arboresce_ffi" not in result.stdout
        ):
            raise ValueError(
                f"JVM {kind} native library must fail to load:\n{result.stdout}"
            )
        if kind == "wrong-architecture" and not re.search(
            r"architecture|ELFCLASS|wrong ELF|cannot open shared object", result.stdout
        ):
            raise ValueError(
                f"JVM wrong-architecture failure lacks a loader diagnostic:\n{result.stdout}"
            )
        print(f"PASS: JVM rejects {kind} native library without fallback")


def test_kotlin_consumer(sdk=SDK, artifacts=None):
    repository = Path(artifacts) if artifacts is not None else sdk / "build/dist/maven"
    with tempfile.TemporaryDirectory(prefix="arboresce-jvm-consumer-") as temporary:
        root = Path(temporary)
        consumer = root / "consumer"
        shutil.copytree(sdk / "tests/consumers/kotlin", consumer)
        shutil.copytree(
            sdk / "bindings/kotlin/lib/src/test",
            consumer / "src/test",
            dirs_exist_ok=True,
        )
        if repository.is_file():
            extract_zip(repository, root / "maven")
        else:
            shutil.copytree(repository, root / "maven")
        validate_maven(sdk=sdk, artifacts=root / "maven")
        run(
            [
                sdk / "bindings/kotlin/gradlew",
                "--no-daemon",
                "test",
                "copyRuntimeDependencies",
            ],
            cwd=consumer,
        )
        fixture = consumer / "Consumer.java"
        shutil.copyfile(sdk / "tests/platforms/fixtures/jvm/Consumer.java", fixture)
        output = consumer / "java8-classes"
        output.mkdir()
        jar = (
            root
            / f"maven/ai/arboresce/arboresce/{version(sdk)}/arboresce-{version(sdk)}.jar"
        )
        run(
            ["javac", "--release", "8", "-cp", jar, "-d", output, fixture], cwd=consumer
        )
        classpath = f"{output}{os.pathsep}{consumer / 'build/runtime/*'}"
        java8 = java8_executable()
        for executable in filter(None, ["java", java8]):
            result = run(
                [executable, "-Djna.nosys=true", "-cp", classpath, "Consumer"],
                cwd=consumer,
                capture=True,
            )
            if result.stdout != "Arboresce\n":
                raise ValueError(
                    f"Unexpected plain Java consumer output: {result.stdout}"
                )
            identity = run([executable, "-version"], capture=True)
            print(f"PASS: Plain Java consumer: {identity.stdout.splitlines()[0]}")
        if java8 is None:
            print(
                "UNQUALIFIED: Java 8 execution unavailable; --release 8 compilation and Java 21 execution passed"
            )
        test_jvm_loading(consumer, sdk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "npm-pack",
            "npm-test",
            "npm-browser-test",
            "go-pack",
            "go-test",
            "maven-check",
            "android-check",
            "kotlin-test",
        ),
    )
    parser.add_argument("--artifacts", type=Path)
    arguments = parser.parse_args()
    command = arguments.command
    if command == "npm-pack":
        package_typescript()
    elif command == "npm-test":
        test_typescript_consumer(artifacts=arguments.artifacts)
    elif command == "npm-browser-test":
        test_typescript_consumer(browser=True, artifacts=arguments.artifacts)
    elif command == "go-pack":
        build_go_distribution()
    elif command == "go-test":
        test_go_consumer(artifacts=arguments.artifacts)
    elif command == "maven-check":
        validate_maven(artifacts=arguments.artifacts)
    elif command == "android-check":
        validate_maven(android=True, artifacts=arguments.artifacts)
    elif command == "kotlin-test":
        test_kotlin_consumer(artifacts=arguments.artifacts)


if __name__ == "__main__":
    main()
