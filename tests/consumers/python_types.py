import subprocess
import sys
from pathlib import Path

SDK = Path(__file__).resolve().parents[2]


def check(python):
    python = Path(python).absolute()
    mypy = SDK / "build/checks/bin/mypy"
    command = [
        str(mypy),
        "--python-executable",
        str(python),
        "--no-incremental",
        "--cache-dir",
        str(SDK / "build/mypy"),
    ]
    fixtures = SDK / "bindings/python/tests/types"
    subprocess.run([*command, str(fixtures / "valid.py")], cwd=SDK, check=True)
    invalid = subprocess.run(
        [*command, str(fixtures / "invalid.py")],
        cwd=SDK,
        text=True,
        capture_output=True,
    )
    if (
        invalid.returncode != 1
        or invalid.stdout.count(": error:") != 1
        or "[assignment]" not in invalid.stdout
    ):
        raise ValueError(
            f"Unexpected Python negative consumer result: {invalid.stdout}{invalid.stderr}"
        )
    print(
        "PASS: Installed Python public types, including rejection of an invalid assignment"
    )


if __name__ == "__main__":
    check(sys.argv[1])
