# Arboresce SDKs

Multi-language SDKs for [Arboresce](https://github.com/arboresce/arboresce).

This repository provides C, C++, Go, Kotlin/Java, Python, Swift and TypeScript
bindings to the canonical Rust implementation.

Version 0.0.0 is under development and has not been published. The current
bindings expose name and print-name operations.

## Repository

| Directory | Purpose |
| --- | --- |
| `bindings/` | Language facades, generated bindings, package manifests and tests |
| `crates/` | Rust adapters for UniFFI, Node.js, WebAssembly and the public C ABI |
| `scripts/` | Developer commands for generation, builds, tests and local packaging |
| `tests/` | Installed-package consumers, platform tests and intended target metadata |
| `.github/` | Build and test workflows |

Python and Swift package manifests live at the repository root.

Start with [Developers](DEVELOPERS.md) for prerequisites, commands and intended
platform targets. Each language directory contains its own usage README.

## License

Original project material is available under either the
[MIT License](LICENSE-MIT) or the [Apache License 2.0](LICENSE-APACHE),
at your option.
