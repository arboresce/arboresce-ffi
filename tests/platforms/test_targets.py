import json
import shutil
import tempfile
import unittest
from pathlib import Path

import targets


class TargetPolicy(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = Path(__file__).resolve().parents[2]
        for name in (
            "tests/platforms/targets.json",
            "Cargo.toml",
            "README.md",
            "DEVELOPERS.md",
            "bindings/typescript/package.json",
            "bindings/go/native-platforms.json",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, path)

    def test_summary_is_standalone_and_detects_drift(self):
        readme = (self.root / "README.md").read_bytes()
        targets.update(self.root)
        targets.update(self.root, check=True)
        path = self.root / "DEVELOPERS.md"
        original = path.read_text()
        path.write_text(path.read_text().replace("Runtime test targets", "Qualified"))
        changed = path.read_text()
        with self.assertRaisesRegex(ValueError, "summary differs"):
            targets.update(self.root, check=True)
        self.assertEqual(path.read_text(), changed)
        targets.update(self.root)
        self.assertEqual(path.read_text(), original)
        self.assertEqual((self.root / "README.md").read_bytes(), readme)

    def test_planned_npm_platform_cannot_ship(self):
        path = self.root / "tests/platforms/targets.json"
        data = json.loads(path.read_text())
        data["languages"]["typescript"]["targets"]["macos-arm64"]["intent"] = "planned"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "cannot be distributed"):
            targets.load(self.root)

    def test_public_policy_cannot_assert_qualification(self):
        path = self.root / "tests/platforms/targets.json"
        data = json.loads(path.read_text())
        data["languages"]["go"]["targets"]["macos-arm64"]["qualified"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "cannot assert"):
            targets.load(self.root)
