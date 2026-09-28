import argparse
import json
import platform
import sys
import unittest
from pathlib import Path


def check(tests, identity):
    suite = unittest.TestLoader().discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped or not result.testsRun:
        raise AssertionError("Installed Python suite must pass without skips")
    if identity is not None:
        identity.write_text(
            json.dumps(
                {
                    "python": sys.version,
                    "architecture": platform.machine(),
                    "os": platform.platform(),
                }
            )
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tests", type=Path)
    parser.add_argument("--identity", type=Path)
    arguments = parser.parse_args()
    check(arguments.tests, arguments.identity)


if __name__ == "__main__":
    main()
