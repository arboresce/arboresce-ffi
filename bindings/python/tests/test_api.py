import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import arboresce


class ArboresceTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(arboresce.NAME, "Arboresce")
        self.assertEqual(arboresce.name(), "Arboresce")

    def test_repeated_calls(self):
        self.assertEqual([arboresce.name() for _ in range(1000)], ["Arboresce"] * 1000)

    def test_concurrent_calls(self):
        def names(_):
            return [arboresce.name() for _ in range(128)]

        with ThreadPoolExecutor(max_workers=8) as executor:
            for values in executor.map(names, range(8)):
                self.assertEqual(values, ["Arboresce"] * 128)

    def test_print_name(self):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).parent / "helpers/print_name.py"),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Arboresce\n")
        self.assertEqual(result.stderr, "")
