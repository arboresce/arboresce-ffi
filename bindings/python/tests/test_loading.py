import shutil
import struct
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path

import arboresce


class InstalledLoading(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="arboresce installed ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = self.root / "consumer environment"
        venv.EnvBuilder(with_pip=False).create(self.environment)
        self.python = self.environment / "bin/python"
        site = next((self.environment / "lib").glob("python*/site-packages"))
        self.package = site / "arboresce"
        shutil.copytree(Path(arboresce.__file__).parent, self.package)
        self.library = next(
            path
            for path in self.package.rglob("*arboresce_ffi*")
            if path.suffix in {".so", ".dylib", ".dll"}
        )

    def run_consumer(self):
        return subprocess.run(
            [self.python, "-I", Path(__file__).parent / "helpers/print_name.py"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_relocated_installed_package_in_path_with_spaces(self):
        result = self.run_consumer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Arboresce\n")

    def test_installed_facade_typing_files(self):
        self.assertTrue((self.package / "__init__.pyi").is_file())
        self.assertTrue((self.package / "py.typed").is_file())

    def test_missing_native_library(self):
        self.library.unlink()
        result = self.run_consumer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arboresce_ffi", result.stderr)

    def test_wrong_native_architecture(self):
        data = bytearray(self.library.read_bytes())
        if data[:4] == b"\x7fELF":
            machine = struct.unpack_from("<H", data, 18)[0]
            struct.pack_into("<H", data, 18, 62 if machine == 183 else 183)
        elif data[:4] == b"\xcf\xfa\xed\xfe":
            machine = struct.unpack_from("<I", data, 4)[0]
            struct.pack_into(
                "<I", data, 4, 0x01000007 if machine == 0x0100000C else 0x0100000C
            )
        else:
            self.fail("Expected a declared ELF or Mach-O wheel library")
        self.library.write_bytes(data)
        result = self.run_consumer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arboresce_ffi", result.stderr)
