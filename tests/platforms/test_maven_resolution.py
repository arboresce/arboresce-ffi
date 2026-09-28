import subprocess
import tempfile
import unittest
from pathlib import Path

SDK = Path(__file__).resolve().parents[2]


class MavenResolution(unittest.TestCase):
    def test_prepared_sdk_coordinates_never_resolve_from_another_repository(self):
        settings = (
            SDK / "bindings/kotlin/android-smoke/settings.gradle.kts"
        ).read_text()
        for present in (True, False):
            with (
                self.subTest(prepared=present),
                tempfile.TemporaryDirectory(
                    prefix="arboresce-maven-selection-"
                ) as temporary,
            ):
                root = Path(temporary)
                for repository in ("repository", "shadow"):
                    base = root / repository / "ai/arboresce/arboresce/0.0.0"
                    base.mkdir(parents=True)
                    if repository == "repository" and not present:
                        continue
                    (base / "arboresce-0.0.0.pom").write_text(
                        "<project><modelVersion>4.0.0</modelVersion>"
                        "<groupId>ai.arboresce</groupId>"
                        "<artifactId>arboresce</artifactId>"
                        "<version>0.0.0</version></project>"
                    )
                    (base / "arboresce-0.0.0.jar").write_text(repository)
                (root / "settings.gradle.kts").write_text(
                    settings.replace(
                        "google()", 'maven { url = uri("shadow") }'
                    ).replace("mavenCentral()", 'maven { url = uri("shadow") }')
                )
                (root / "build.gradle.kts").write_text(
                    "val probe by configurations.creating\n"
                    'dependencies { add("probe", "ai.arboresce:arboresce:0.0.0") }\n'
                    'tasks.register("verifySelection") { doLast {\n'
                    "val content = probe.singleFile.readText()\n"
                    'check(content == "repository") { "WRONG_REPOSITORY" }\n'
                    'println("PREPARED_REPOSITORY_SELECTED")\n'
                    "} }\n"
                )
                result = subprocess.run(
                    [
                        str(SDK / "bindings/kotlin/gradlew"),
                        "--no-daemon",
                        "--offline",
                        "verifySelection",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                output = result.stdout + result.stderr
                if present:
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn("PREPARED_REPOSITORY_SELECTED", output)
                else:
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("Could not find ai.arboresce:arboresce:0.0.0", output)
                    self.assertNotIn("WRONG_REPOSITORY", output)
