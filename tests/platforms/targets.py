import argparse
import json
import tomllib
from pathlib import Path


def load(root):
    data = json.loads((root / "tests/platforms/targets.json").read_text())
    if data["schema"] != 1:
        raise ValueError("Unsupported target matrix schema")
    for language, value in data["languages"].items():
        for target, policy in value["targets"].items():
            if (
                target not in data["platforms"]
                or policy["intent"] not in {"runtime", "link", "planned"}
                or not policy["effective_minimum"]
            ):
                raise ValueError(f"Invalid target policy: {language}/{target}")
            if {"qualified", "build"} & policy.keys():
                raise ValueError(
                    "Public target policy cannot assert private qualification"
                )
    version = tomllib.loads((root / "Cargo.toml").read_text())["workspace"]["package"][
        "version"
    ]
    npm = json.loads((root / "bindings/typescript/package.json").read_text())
    if npm.get("optionalDependencies") != {
        item["name"]: version for item in data["node_packages"].values()
    }:
        raise ValueError("npm distribution inventory differs from public targets")
    expected_targets = {
        data["platforms"][target]["rust"] for target in data["node_packages"]
    }
    actual_targets = npm.get("napi", {}).get("targets", [])
    if set(actual_targets) != expected_targets or len(actual_targets) != len(
        expected_targets
    ):
        raise ValueError("napi build targets differ from public targets")
    for target in data["node_packages"]:
        if data["languages"]["typescript"]["targets"][target]["intent"] == "planned":
            raise ValueError("Planned npm targets cannot be distributed")
    go = json.loads((root / "bindings/go/native-platforms.json").read_text())
    if set(go["platforms"].values()) != {
        data["platforms"][target]["rust"]
        for target in data["languages"]["go"]["targets"]
    }:
        raise ValueError("Go inventory differs from public targets")
    return data


def table(root):
    data = load(root)
    rows = [
        "| SDK | Runtime test targets | Build/link targets | Planned |",
        "| --- | --- | --- | --- |",
    ]
    for name, language in data["languages"].items():
        cells = [
            ", ".join(
                target
                for target, value in language["targets"].items()
                if value["intent"] == intent
            )
            or "None"
            for intent in ("runtime", "link", "planned")
        ]
        rows.append("| " + " | ".join([name, *cells]) + " |")
    rows += [
        "",
        "These are intended test targets, not release qualification claims. The public",
        "matrix records native deployment and effective runtime floors separately. Runtime",
        "tests on a newer OS do not establish minimum-OS support. Private release receipts",
        "record the actual artifact, compiler, host, emulation and executed checks.",
        "",
        "Go 1.27 requires macOS 13 or later. Node 22 Linux consumers require glibc 2.28",
        "and kernel 4.18 or later even when the native library targets glibc 2.17.",
        "Java 8 bytecode does not by itself establish Java 8 runtime compatibility.",
    ]
    return "\n".join(rows)


def update(root, check=False):
    path = root / "DEVELOPERS.md"
    text = path.read_text()
    start, end = "<!-- support:start -->", "<!-- support:end -->"
    section = start + "\n" + table(root) + "\n" + end
    if start not in text or end not in text:
        raise ValueError("Missing public support section")
    updated = text[: text.index(start)] + section + text[text.index(end) + len(end) :]
    if check and updated != text:
        raise ValueError("Public support summary differs; run make update-support")
    if not check:
        path.write_text(updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    update(Path(__file__).resolve().parents[2], arguments.check)
