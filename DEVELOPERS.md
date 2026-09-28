# Developers

Arboresce SDKs wrap the [Rust engine](https://github.com/arboresce/arboresce)
through UniFFI, napi-rs, wasm-bindgen and a separately versioned C ABI.
The implemented operations return and print the project name. No engine objects,
queries, callbacks or async runtime are exposed yet.

## Development commands

Run commands from a standalone checkout. `make help` lists the available tasks.
All Make targets delegate to `scripts/make.sh` and work without required arguments
or environment overrides. Activate the pinned toolchains before setup.

Install Rust 1.98.1 through rustup and have jq available for every language.
The language-specific prerequisites and commands are listed below.

To work on all bindings on macOS with Xcode and every language toolchain installed:

```sh
make setup
make doctor
make generate
make build
make test
make check
make check-generated
```

`make verify` checks prerequisites, formatting, Clippy, ShellCheck and generated
output, then builds and runs all host regression suites. Aggregate commands run
Swift on macOS; Linux runs the other language suites. Explicit Swift commands
require macOS and Xcode. Browser and mobile tests have separate targets.

## Repository structure

- `crates/ffi` provides UniFFI adapters for Python, Kotlin, Swift and Go.
- `crates/node` provides napi-rs adapters for Node.js.
- `crates/wasm` provides wasm-bindgen adapters for browsers.
- `crates/c` provides the C11 ABI directly over the same pinned core.
- `bindings/cpp` provides a header-only C++17 facade over that C ABI.
- `bindings/` contains language facades, generated source and package manifests.

Adapters consume the canonical engine at a full immutable Git revision. Never
copy its implementation here or use floating/path release dependencies. Rust
uses edition 2024 and resolver 3. The workspace version in `Cargo.toml` owns the
SDK version; language package versions must agree. Core and FFI repositories
retain separate histories. Preserve the [package identities](#package-identities);
Go uses `arboresce.ai` for v0/v1
and major-version suffixes from v2. Version tags use `bindings/go/v<version>`
in this repository. HTTPS module discovery maps the module to this repository's
`bindings/go` subdirectory. Published module snapshots add the required native archives;
`master` remains source-only.

## Package identities

| Language | Installation or import |
| --- | --- |
| Rust | `cargo add arboresce` |
| TypeScript | `npm install arboresce` |
| Python | `uv add arboresce` |
| Go | `go get arboresce.ai` |
| Swift | `import Arboresce` |
| Kotlin / Java | `implementation("ai.arboresce:arboresce:<version>")` |
| C | `#include <arboresce/arboresce.h>` |
| C++ | `#include <arboresce/arboresce.hpp>` |

Consult each package registry for current version availability. The canonical Rust SDK is maintained separately in
[arboresce/arboresce](https://github.com/arboresce/arboresce).
Release notes accompany published versions.

## Generated bindings

Edit adapters or generator configuration, never generated output. Run
`make generate` after changing shared generation inputs; it regenerates UniFFI,
Node, WASM and cbindgen-owned C bindings and compiles TypeScript with tsc. Individual UniFFI targets
are `make generate-python`, `make generate-kotlin`, `make generate-swift` and
`make generate-go`.

`make check-generated` compares fresh output byte for byte without rewriting
source. It needs the pinned generators, jq, Node and wasm-pack, but does not need
Swift or Java compilers. Preserve upstream generator comments and required
compiler directives. Handwritten SDK source has no comments or docstrings;
keep explanations in Markdown documentation.

## Testing and validation

`make test` builds and runs the host regression suites. Tests exercise the public
API: identity, repeated calls, concurrent callers and exact print output. Browser
WASM also checks explicit initialization; TypeScript checks consumer types. Go
runs its race detector. These checks are not a thread-safety proof or benchmark.

| Scope | Test location | Runner |
| --- | --- | --- |
| Rust adapter | `crates/ffi/tests/` | Cargo |
| Python | `bindings/python/tests/` | unittest |
| TypeScript | `bindings/typescript/test/` | node:test and tsc |
| Kotlin | `bindings/kotlin/lib/src/test/kotlin/` | JUnit 5 |
| Go | `bindings/go/*_test.go`, helpers in `testdata/` | go test -race |
| Swift | `bindings/swift/Tests/` | XCTest |
| Platforms | `tests/platforms/`, `bindings/kotlin/android-smoke/` | Native consumers and emulators |

`make setup-checks` installs the locked formatter/type-checker group.
`make check` runs Rust formatting/Clippy, ShellCheck, Ruff, Prettier/tsc, gofmt/vet,
ktfmt, clang-format and Swift formatting on macOS. `make format` formats
handwritten source only. Per-language `check-<language>` and `format-<language>`
targets select narrower checks (Rust formatting uses `make format`).
Ruff 0.16.9, Mypy 2.3.1 and clang-format 21.1.0 are locked by `uv.lock`; Prettier
3.6.2 is locked by npm; ktfmt 0.58 is verified against a fixed SHA-256; Swift
format comes from the selected Swift toolchain. New APIs need equivalent tests across languages,
including errors and cleanup. Generated code is never edited to satisfy a test.

Build/test CI invokes the same Make commands without publishing credentials.
Platform tests fail when a requested prerequisite is unavailable. Cross-compilation
is not runtime qualification; keep the [target summary](#intended-targets) accurate.

Local package builds, test fixtures and development CI belong here. Credentials,
signing, registry uploads, release promotion and frozen release evidence are
maintained externally. Release qualification reuses these test sources against
isolated packages. Build output remains ignored.

## Per-language development

### Rust adapters

Requires Rust 1.98.1, rustup and jq. The repository uses edition 2024 and resolver 3.

```sh
make setup-rust
make doctor-rust
make build-rust
make test-rust
```

This builds the UniFFI library and generator. The Node and WASM adapters are built
by their TypeScript commands below. Adapter tests exercise the FFI boundary;
canonical engine tests remain in the engine repository.

### Python

Requires Python 3.14.7 and uv, in addition to the shared Rust prerequisites.
Setup creates the build environment and installs the pinned maturin and
cross-build helpers.

```sh
make setup-checks
make setup-python
make doctor-python
make generate-python
make build-python
make test-python
```

The build regenerates the binding and produces a native wheel. The unittest suite
installs that wheel into an isolated environment and checks the public API,
relocation into a path containing spaces, and missing/wrong-architecture libraries.
The facade-owned `__init__.pyi` and `py.typed` ship in the wheel. Mypy tests the
installed package with positive and negative consumers; generator output is
excluded from handwritten formatting. Each install bypasses cached wheels for
the same development version. Native wheel tags do not imply pure Python, abi3,
free-threaded support or support below the declared Python 3.14 floor.
For Linux cross-build prerequisites, run `make setup-linux`.

### TypeScript: Node.js and browser WASM

Requires Node 22.22.3 and npm, in addition to the shared Rust prerequisites.
Setup installs locked npm dependencies, pinned wasm-pack and the Rust WASM target.

```sh
make setup-typescript
make doctor-typescript
make build-typescript
make test-node
make test-wasm
```

The build generates the napi-rs Node addon and wasm-bindgen browser module, then
compiles the public TypeScript facades with tsc. `make build-node` and
`make build-wasm` rebuild the individual native/WASM outputs. Run the full
TypeScript build after changing facade source. Handwritten entry points live in
`bindings/typescript/src`; `native/` and `wasm/` contain generator-owned glue and
declarations, with ignored binaries beside them. Compiled facades live in ignored
`dist/`. `test/node.test.ts` exercises the Node addon; `test/wasm.test.ts` exercises
the browser interface under Node; `test/browser/chromium.test.mjs` runs Chromium.

`make package-typescript` generates native package manifests with the pinned
napi-rs CLI into ignored `build/typescript/npm/<platform-arch-abi>/`, validates
them against `tests/platforms/targets.json`, and adds licenses and available
binaries. The generator reads a staged copy of the source package manifest.
Platform packages retain the original license texts as `LICENSE.MIT` and
`LICENSE.APACHE`, names npm includes automatically without modifying generated
manifests. The main package retains `LICENSE-MIT` and `LICENSE-APACHE`.
The staging tree is recreated on each package run so removed targets cannot
persist. `make package-typescript-all` builds the complete declared native matrix
on macOS with Zig. Both commands write local archives to `build/dist/npm/`;
neither publishes them. Platform manifests and binary copies do not live under
`bindings/typescript/npm/`. Public entry points and native package names remain
defined by `bindings/typescript/package.json`.

`make test-tooling` runs package and platform helper regressions, including real
napi-rs package generation and npm archive checks. It requires uv/Python and
`make setup-typescript`; CI runs it in the TypeScript job with those prerequisites.

The browser `initialize()` shares its in-flight promise and is idempotent after
success. A failed attempt clears state so an explicit retry can succeed. Calls
to `name()` and `printName()` require completed initialization. Browser printing
uses `console.log`; native printing uses core stdout. The browser entry is web
WASM, not WASI.

For real browser tests:

```sh
make setup-browser
make test-browser
```

Setup installs pinned Playwright and Chromium. On Linux it also installs the
required OS libraries through Playwright and may require sudo.

### Kotlin: JVM and Android

Requires Java 21, including javac, in addition to the shared Rust prerequisites.
Use the checked-in Gradle wrapper; no global Gradle installation is needed.
The root Gradle project contains the `:lib` JVM module. Its public facade and
generated `ai.arboresce.internal` bindings live in `bindings/kotlin/lib/src/main/kotlin`;
native libraries are staged under `lib/src/main/resources`.

```sh
make setup-kotlin
make doctor-kotlin
make generate-kotlin
make build-kotlin
make test-kotlin
```

The build regenerates Kotlin bindings and packages the host native library with
the JVM SDK. JUnit tests run against the public facade; the subprocess helper
lives in the test source set and is excluded from the library JAR.
Java uses the same facade: `Arboresce.NAME`, `Arboresce.name()` and
`Arboresce.printName()`. JNA is an implementation dependency retained in runtime
metadata, not a facade compile dependency. The generated `ai.arboresce.internal`
package is an unsupported implementation detail; its name does not enforce JVM
visibility. Java 8 bytecode is distinct from Java 8 runtime qualification.
Installed-consumer tests exercise plain Java, Kotlin, native extraction and
loading failures.

Android additionally requires NDK r30 and SDK platform 36 in the standard SDK
installation. To prepare Rust targets and build the Android package:

```sh
make setup-android
make build-android-aar
```

Android remains a separate build under `bindings/kotlin/android`. Its composite
build substitutes `ai.arboresce:arboresce` with the local `:lib` project, so JVM
development needs no Android SDK. Published coordinates remain
`ai.arboresce:arboresce` and `ai.arboresce:arboresce-android`.
`make test-android` builds and runs the app under `android-smoke` on an emulator.
Install Android command-line tools, platform-tools, build-tools 36.0.0, emulator,
and an Android 36 Google APIs 16 KiB page-size system image matching the host
architecture (arm64-v8a or x86_64). This command also requires uv and Python
3.14.7. It reserves a free emulator port, creates/removes only its own virtual
device, and requires `getconf PAGE_SIZE` to return 16384. Every packaged Rust
and JNA library is checked for architecture/alignment and the final APK is
checked with `zipalign -P 16`. Ordinary 4 KiB emulator execution does not pass
this qualification.

### Go

Requires Go 1.27.1, CGO and a C compiler, in addition to the shared Rust
prerequisites. Setup installs the pinned Go generator; run it before the doctor
on a fresh checkout.

```sh
make setup-go
make doctor-go
make generate-go
make build-go
make test-go
```

The build regenerates bindings and compiles the host native library and Go
package. Tests use the external `arboresce_test` package and only the public API.
The generator uses Cargo's debug profile to keep setup fast; native SDK libraries
use release builds. `make check-go-generator` verifies the generator pin.

### Swift

Requires macOS, Xcode and Swift 6.3, in addition to the shared Rust prerequisites.
Setup installs the Apple Rust targets.

```sh
make setup-swift
make doctor-swift
make generate-swift
make build-swift
make check-swift-local
make test-swift
```

The build regenerates Swift bindings, assembles the five Apple native slices into
an XCFramework and stages `bindings/swift/dev/Package.swift` with canonical
Sources/Tests into `build/swift-dev`. Swift build/test runs in that staged package. XCTest runs against the public
module. Its print helper is a test dependency, not a public executable product.
The subprocess test is macOS-only; mobile runtime checks use a separate fixture.

```sh
make test-ios
make test-swift-platforms
```

These commands require uv, Python 3.14.7 and an installed iOS simulator runtime
and a compatible available iPhone device type. The fixture discovers installed
runtimes and selects the simulator architecture for the current host.
The additional macOS x64 runtime check requires Rosetta on Apple Silicon.
Device and simulator link checks do not establish runtime support.

The public Arboresce module wraps ArboresceBindings and the ArboresceNative binary
target. The local check rejects stale or altered XCFrameworks; fresh consumers
use the versioned asset and checksum in `Package.swift`. The root manifest
always selects that URL/checksum, irrespective of local files or environment.
`make package-swift` produces unsigned local ZIPs; it never publishes an asset.

### C11 and C++17

Requires Rust 1.98.1, a C11 compiler, CMake 3.24+, pkg-config and uv/Python 3.14.7.
C++ additionally requires a C++17 compiler. `make setup-c` installs cbindgen
0.29.4 with Cargo's locked dependency graph. `make setup-cpp` checks both compilers.

```sh
make setup-cpp
make generate-c
make check-generated-c
make test-c
make test-cpp
make package-c
make package-cpp
```

`make install-c` creates `build/native/install`. CMake consumers use
`find_package(Arboresce CONFIG REQUIRED)` and `Arboresce::c_shared`,
`Arboresce::c_static` or the shared-default `Arboresce::c`. The C package config
works in a C-only project. pkg-config consumers use `arboresce`; static linkage
requires `pkg-config --static`. Native system libraries are captured from the
actual Rust build. The installed prefix relocates without SDK source or Rust.

C++ consumers use `find_package(ArboresceCpp CONFIG REQUIRED)` and
`Arboresce::cpp` or `Arboresce::cpp_static`. The facade is a header, with C++17
and linkage requirements attached to interface targets. Its package depends on
the exact corresponding C package. Both linkages are tested with exceptions
disabled; no C++ ABI is exported by Rust.

The C ABI version is `0x00010000`. Its only public symbols are
`arboresce_v1_abi_version`, `arboresce_v1_name` and `arboresce_v1_print_name`.
`arboresce_status` is a 32-bit unsigned integer: 0 is success, 1 invalid argument,
and 2 a caught Rust panic. Callers must preserve unknown nonzero status values
as errors. The public C header is generated from `crates/c`; the UniFFI bridge
headers are private generator contracts and are not this ABI.

For `arboresce_v1_name`, a null output pointer returns invalid argument. A
non-null pointer must reference live, writable, properly aligned storage for one
`arboresce_string_view`; the caller must prevent simultaneous conflicting
accesses. A null check cannot validate an arbitrary address. Valid output storage
is reset to `{NULL, 0}` before fallible work. Success returns a borrowed immutable
UTF-8 byte view with an explicit byte length. It is not guaranteed NUL-terminated;
do not free or modify it, or call `strlen`. The view lasts only while the native
library remains loaded. Concurrent calls with distinct output storage may read
the static name; unloading while any call or borrowed view remains live is unsafe.

The dedicated `c-release` profile uses unwinding and rejects an abort-strategy
build. Each fallible export catches ordinary Rust panics; stdout failures may
therefore return panic status. This does not contain invalid pointers, signals,
allocation aborts or foreign exceptions. A panic while dropping a panic payload
can abort at the foreign boundary; a subprocess regression records this behavior.
The default panic hook may write diagnostics. A caught panic is not a promise
that future stateful engine objects remain usable. No arbitrary-pointer tests
invoke undefined behavior in the normal suite.

C++ `name()` returns a `name_result` containing status plus borrowed
`std::string_view`; failure returns an empty view without converting a failed
pointer. Both wrapper functions are `noexcept`, preserve status and allocate
nothing. They retain the C view's library lifetime restriction.

`test-c-static`, `test-c-shared`, `test-c-abi`, `test-c-consumer`,
`test-cpp-consumer` and `test-cpp-no-exceptions` isolate checks. The versioned ABI
baseline covers symbol inventory and 32/64-bit layouts. Actual executed targets
are recorded separately; a recorded 32-bit layout does not claim a 32-bit run.
C caller ASan/UBSan checks do not instrument Rust. Go's race detector similarly
does not establish Rust race freedom. macOS dylib install names and ELF SONAMEs
carry ABI major 1. Windows is not yet packaged or qualified.

## Local packages and target policy

TypeScript build tools use the private root `package.json` and its lockfile.
`make setup-typescript` installs only those tools; the publishable facade keeps
its native optional dependencies in `bindings/typescript/package.json`. Bootstrap
does not resolve SDK packages from npm, including for unpublished versions.

`package-python`, `package-typescript`, `package-kotlin`, `package-android`,
`package-go`, `package-swift`, `package-c` and `package-cpp` create unsigned
artifacts under `build/dist`. `package-typescript-all` and `package-kotlin-all`
prepare the declared macOS/Linux native inventories on a macOS cross-build host.
JVM and Android Gradle publication tasks only write a local Maven repository.
Registry publication and signing remain external.

`test-typescript-consumer`, `test-browser-consumer`, `test-kotlin-consumer`,
`test-go-consumer` and `test-swift-consumer` use isolated installed packages.
Python wheel and C/C++ installed-prefix checks are part of their normal tests.
TypeScript consumers first install their locked test tools with `npm ci`, which
requires registry access on a fresh cache. They then install the local SDK
tarballs offline; an unpublished SDK version can be tested without registry
access for any SDK package. Hosted CI exercises this with a separate fresh cache.
Go packages contain every declared static archive and validate receipts for the
core revision, generator revision/binary, compiler and source inputs before ZIP
creation. Consumers resolve the prepared module using a local file-backed proxy.

`tests/platforms/targets.json` owns intended targets, native deployment floors,
and effective per-language floors. `make update-support` regenerates the
[target summary](#intended-targets) in this document without private files;
`make check-support` rejects drift. Intent is not
execution evidence. Minimum-OS tests, host execution, emulation and link-only
checks must be reported separately. Current Go 1.27 requires macOS 13+, and
Node 22 Linux requires glibc 2.28/kernel 4.18 even where Rust targets glibc 2.17.
macOS Java 8, minimum macOS/iOS/Android runtimes and other unexecuted environments
remain unqualified until actual installed-package runs establish them.

### Intended targets

Native deployment baselines are macOS 11, iOS 13, glibc 2.17 and Android API 28.
The JVM artifact targets Java 8 bytecode; builds use Java 21. Baselines do not
imply testing on every historical OS version.

<!-- support:start -->
| SDK | Runtime test targets | Build/link targets | Planned |
| --- | --- | --- | --- |
| python | macos-arm64, linux-arm64, linux-x64 | None | macos-x64, windows-x64 |
| typescript | macos-arm64, macos-x64, linux-arm64, linux-x64, browser | None | windows-x64 |
| kotlin | macos-arm64, linux-arm64, linux-x64 | macos-x64 | windows-x64 |
| android | android-arm64 | android-armv7, android-x64 | None |
| swift | macos-arm64, macos-x64, ios-sim-arm64 | ios-arm64, ios-sim-x64 | None |
| go | macos-arm64, macos-x64, linux-arm64, linux-x64 | None | None |
| c | macos-arm64, macos-x64, linux-arm64, linux-x64 | None | None |
| cpp | macos-arm64, macos-x64, linux-arm64, linux-x64 | None | None |

These are intended test targets, not release qualification claims. The public
matrix records native deployment and effective runtime floors separately. Runtime
tests on a newer OS do not establish minimum-OS support. Private release receipts
record the actual artifact, compiler, host, emulation and executed checks.

Go 1.27 requires macOS 13 or later. Node 22 Linux consumers require glibc 2.28
and kernel 4.18 or later even when the native library targets glibc 2.17.
Java 8 bytecode does not by itself establish Java 8 runtime compatibility.
<!-- support:end -->

## Cross-platform development

On macOS with Docker, Zig and the relevant toolchains installed:

```sh
make setup-linux
make test-linux
make test-go-platforms
```

Installed Linux consumers run in arm64 and x86_64 containers. JVM checks compile
and run on Java 8 and Java 21; the host JVM tests use Java 21. The full Go matrix also
executes both macOS architectures and checks unsupported configurations.
Docker needs emulation for non-host architectures. These commands use local
builds and public container images, not release candidates or registry credentials.

## API changes

Before exporting an API, define ownership, lifetime, thread safety and cleanup,
including repeated close, use after close and in-flight behavior where relevant.
Use stable public error categories and idiomatic language errors, keep internal
Rust details private, and avoid panics for expected errors. Use bounded batches
for large collections and document copying costs.

Keep generated namespaces behind public facades and configure language-specific
names through the generators. Add callback or async machinery only when the
engine needs it. Callbacks must define retention, execution context, backpressure
and removal; async APIs must define cancellation, completion races and shutdown.

## Future API gates

Keep current adapters independent. Add a shared policy crate only when repeated
substantive policy warrants it. Before adding resources, specify ownership and
close/use races, panic recovery, Send/Sync, fork/unload behavior, callbacks and
bounded cancellation/streaming. The current stateless tests establish none of
those engine properties. Do not add constructors, handle registries, custom
allocators or async machinery ahead of implemented core operations. Java remains
a consumer of the existing JVM artifact. .NET is the next prospective direct
C-ABI binding; additional language implementations are deferred.

## Prepared platform consumers

`test-packaged-go`, `test-packaged-swift`, `test-packaged-ios`,
`test-packaged-android`, `test-packaged-c` and `test-packaged-cpp` run the platform
assertions against existing packages without rebuilding SDK libraries. Set
`ARBORESCE_PACKAGE_ROOT` to the prepared artifact directory; it defaults to
`build/dist`. These checks require the same host runtimes as their build-and-test
counterparts and fail when a required artifact or runtime is unavailable.
