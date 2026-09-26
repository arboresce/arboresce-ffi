#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
export PATH="$ROOT/build/tools/bin:$PATH"

die() { printf '%s\n' "$*" >&2; exit 1; }
require() { command -v "$1" >/dev/null || die "Required tool is missing: $1"; }
target_dir() { cargo metadata --locked --no-deps --format-version 1 | jq -r .target_directory; }
library() {
    case $(uname -s) in
        Darwin) printf '%s/debug/libarboresce_ffi.dylib\n' "$(target_dir)" ;;
        Linux) printf '%s/debug/libarboresce_ffi.so\n' "$(target_dir)" ;;
        *) die 'Use a declared native build target for this host' ;;
    esac
}
doctor_rust() {
    require cargo; require rustc; require jq
    [[ $(rustc --version) == 'rustc 1.98.1 '* ]] || die 'Rust 1.98.1 is required'
}
doctor_python() {
    doctor_rust
    require uv
    uv python find --system 3.14.7 >/dev/null
}
doctor_typescript() {
    doctor_rust
    require node; require npm
    [[ $(node --version) == v22.22.3 ]] || die 'Activate Node 22.22.3 before running TypeScript commands'
}
verify_node_generator() {
    local installed=bindings/typescript/node_modules/@napi-rs/cli/package.json
    [[ -f "$installed" ]] || die 'Run make setup-typescript before building'
    [[ $(jq -r .version "$installed") == "$(jq -r '.devDependencies["@napi-rs/cli"]' bindings/typescript/package.json)" ]] || die 'Node generator version differs; run make setup-typescript'
}
doctor_wasm() {
    doctor_typescript
    require wasm-pack
    [[ $(wasm-pack --version) == 'wasm-pack 0.15.0' ]] || die 'wasm-pack 0.15.0 is required'
}
doctor_kotlin() {
    doctor_rust
    require java; require javac
    java -version 2>&1 | grep -Eq 'version "21[.]' || die 'Java 21 is required'
}
doctor_swift() {
    doctor_rust
    require swift; require xcodebuild
    swift --version | grep -Eq 'Swift version 6[.]3([. ]|$)' || die 'Swift 6.3 is required'
}
doctor() {
    doctor_python
    doctor_wasm
    doctor_kotlin
    if [[ $(uname -s) == Darwin ]]; then doctor_swift; fi
    doctor_go
    doctor_cpp
}
setup_rust() {
    doctor_rust
    cargo fetch --locked
}
setup_python() {
    doctor_python
    mkdir -p build
    UV_PROJECT_ENVIRONMENT=build/python uv sync --locked --only-group build --no-install-project --python "$(uv python find --system 3.14.7)" --no-python-downloads
}
setup_typescript() {
    doctor_typescript
    npm ci --prefix bindings/typescript --ignore-scripts --no-audit --no-fund
    if ! command -v wasm-pack >/dev/null || [[ $(wasm-pack --version) != 'wasm-pack 0.15.0' ]]; then
        cargo install wasm-pack --version 0.15.0 --locked --root build/tools
    fi
    rustup target add wasm32-unknown-unknown
}
setup_kotlin() {
    doctor_kotlin
    (cd bindings/kotlin && ./gradlew --no-daemon :lib:dependencies)
}
setup_swift() {
    doctor_swift
    rustup target add aarch64-apple-darwin x86_64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios
}
setup() {
    setup_rust
    setup_checks
    setup_cpp
    setup_python
    setup_typescript
    setup_go_generator
    setup_kotlin
    if [[ $(uname -s) == Darwin ]]; then setup_swift; fi
}
build_rust() { doctor_rust; cargo build --locked -p arboresce-ffi --features cli; }
bindgen() { "$(target_dir)/debug/uniffi-bindgen" "$@"; }
generate_python() {
    build_rust
    bindgen generate --no-format --library "$(library)" --language python --config crates/ffi/uniffi.toml --out-dir bindings/python/src/arboresce
}
generate_kotlin() {
    build_rust
    bindgen generate --no-format --library "$(library)" --language kotlin --config crates/ffi/uniffi.toml --out-dir bindings/kotlin/lib/src/main/kotlin
}
generate_swift() {
    build_rust
    bindgen generate --no-format --library "$(library)" --language swift --config crates/ffi/uniffi.toml --out-dir bindings/swift/Sources/ArboresceBindings
}
generate_go() {
    verify_go_generator
    build_rust
    build/tools/bin/uniffi-bindgen-go --library "$(library)" --config crates/ffi/uniffi.toml --out-dir bindings/go/internal
}
verify_go_generator() {
    local version revision repository uniffi installed
    version=$(jq -r .version crates/ffi/go-bindgen.json)
    revision=$(jq -r .revision crates/ffi/go-bindgen.json)
    repository=$(jq -r .repository crates/ffi/go-bindgen.json)
    uniffi=$(jq -r .uniffi crates/ffi/go-bindgen.json)
    [[ -x build/tools/bin/uniffi-bindgen-go && -f build/tools/.crates2.json ]] || die 'Go generator missing; run make setup-go'
    installed=$(build/tools/bin/uniffi-bindgen-go --version)
    [[ "$installed" == "uniffi-bindgen $version" ]] || die 'Go generator version mismatch; run make setup-go'
    jq -e --arg prefix "uniffi-bindgen-go $version (git+$repository?" --arg suffix "#$revision)" \
      '.installs | to_entries | map(select((.key | startswith($prefix)) and (.key | endswith($suffix)) and (.value.bins | index("uniffi-bindgen-go")))) | length == 1' build/tools/.crates2.json >/dev/null || die 'Go generator revision mismatch; run make setup-go'
    [[ -f build/tools/go-generator-rustc.txt && $(cat build/tools/go-generator-rustc.txt) == "$(rustc --version)" ]] || die 'Go generator compiler mismatch; run make setup-go'
    grep -Fxq "uniffi = \"=$uniffi\"" Cargo.toml || die 'UniFFI and Go generator versions are incompatible'
}
setup_go_generator() {
    doctor_rust
    if ! (verify_go_generator) >/dev/null 2>&1; then
        cargo install uniffi-bindgen-go --git "$(jq -r .repository crates/ffi/go-bindgen.json)" --rev "$(jq -r .revision crates/ffi/go-bindgen.json)" --locked --debug --force --root build/tools
        rustc --version > build/tools/go-generator-rustc.txt
    fi
    verify_go_generator
}
go_generator_identity() {
    verify_go_generator
    jq --arg sha256 "$(shasum -a 256 build/tools/bin/uniffi-bindgen-go | cut -d ' ' -f 1)" '. + {binary_sha256:$sha256}' crates/ffi/go-bindgen.json
}
doctor_go() {
    doctor_rust
    require go
    [[ $(go version) == 'go version go1.27.1 '* ]] || die 'Go 1.27.1 is required'
    verify_go_generator
    [[ $(go env CGO_ENABLED) == 1 ]] || die 'Arboresce Go requires CGO_ENABLED=1 and a C compiler'
    jq -e --arg platform "$(go env GOOS)_$(go env GOARCH)" '.platforms | has($platform)' bindings/go/native-platforms.json >/dev/null || die 'Unsupported Go platform; see bindings/go/README.md'
    local compiler
    compiler=$(go env CC)
    require "${compiler%% *}"
}
stage_go_native() {
    local platform=$1 target=$2 archive file digest
    archive="bindings/go/internal/native/lib/$platform/libarboresce_ffi.a"
    mkdir -p "$(dirname "$archive")"
    cp "$(target_dir)/$target/release/libarboresce_ffi.a" "$archive"
    {
        while IFS= read -r file; do
            digest=$(shasum -a 256 "$file" | cut -d ' ' -f 1)
            jq -cn --arg path "$file" --arg sha256 "$digest" '{path:$path,sha256:$sha256}'
        done < <(jq -r '.source_files[]' bindings/go/native-platforms.json)
    } | jq -s --arg platform "$platform" --arg target "$target" \
      --arg sha256 "$(shasum -a 256 "$archive" | cut -d ' ' -f 1)" \
      --arg core_rev "$(cargo metadata --locked --no-deps --format-version 1 | jq -r '.packages[0].dependencies[] | select(.name=="arboresce") | .source | split("rev=")[1]')" \
      --arg rustc "$(rustc --version)" --argjson generator "$(go_generator_identity)" \
      '{schema:1,platform:$platform,rust_target:$target,profile:"release",core_rev:$core_rev,rustc:$rustc,generator:$generator,archive_sha256:$sha256,inputs:.}' > "$archive.json"
}
build_go_platform() {
    local platform=$1 target
    target=$(jq -er --arg platform "$platform" '.platforms[$platform]' bindings/go/native-platforms.json)
    case "$platform" in
        darwin_*) cargo build --locked --release -p arboresce-ffi --target "$target" ;;
        linux_*)
            if [[ "$platform" == "$(go env GOHOSTOS)_$(go env GOHOSTARCH)" && ! -x build/python/bin/cargo-zigbuild ]]; then
                cargo build --locked --release -p arboresce-ffi --target "$target"
            else
                build/python/bin/cargo-zigbuild build --locked --release -p arboresce-ffi --target "$target.2.17"
            fi ;;
        *) die 'Unsupported Go platform' ;;
    esac
    stage_go_native "$platform" "$target"
}
build_go_all() {
    generate_go
    local platform
    while IFS= read -r platform; do build_go_platform "$platform"; done < <(jq -r '.platforms | keys[]' bindings/go/native-platforms.json)
}
build_python() {
    doctor_python
    generate_python
    build/python/bin/maturin build --locked --release --interpreter "$(uv python find --system 3.14.7)" --out build/dist/python
}
build_node() {
    doctor_typescript
    verify_node_generator
    bindings/typescript/node_modules/.bin/napi build --manifest-path crates/node/Cargo.toml --package-json-path bindings/typescript/package.json --platform --release --output-dir bindings/typescript/native --js native.cjs --dts native.d.cts -- --locked
}
build_wasm() {
    doctor_wasm
    wasm-pack build crates/wasm --target web --release --out-dir ../../bindings/typescript/wasm --out-name arboresce_wasm --locked
    printf '' > bindings/typescript/wasm/.npmignore
    rm -f bindings/typescript/wasm/.gitignore
}
build_typescript() {
    build_node
    build_wasm
    npm run build --prefix bindings/typescript
}
stage_kotlin_native() {
    cargo build --locked --release -p arboresce-ffi
    local platform release_library
    release_library=$(library)
    release_library=${release_library/\/debug\//\/release\/}
    case $(uname -s)-$(uname -m) in
        Darwin-arm64) platform=darwin-aarch64 ;;
        Darwin-x86_64) platform=darwin-x86-64 ;;
        Linux-x86_64) platform=linux-x86-64 ;;
        Linux-aarch64) platform=linux-aarch64 ;;
        *) die 'Unqualified JVM native platform' ;;
    esac
    mkdir -p "bindings/kotlin/lib/src/main/resources/$platform"
    cp "$release_library" "bindings/kotlin/lib/src/main/resources/$platform/"
}
build_kotlin() {
    doctor_kotlin
    generate_kotlin
    stage_kotlin_native
    (cd bindings/kotlin && ./gradlew --no-daemon :lib:build)
}
build_go() {
    doctor_go
    [[ $(go env GOOS)_$(go env GOARCH) == "$(go env GOHOSTOS)_$(go env GOHOSTARCH)" ]] || die 'Use make build-go-all for cross builds'
    generate_go
    build_go_platform "$(go env GOOS)_$(go env GOARCH)"
    (cd bindings/go && go build ./...)
}
build_swift() {
    build_swift_apple
    stage_swift_dev
    swift build --package-path build/swift-dev
}
swift_inventory() {
    shasum -a 256 Cargo.toml Cargo.lock rust-toolchain.toml crates/ffi/Cargo.toml crates/ffi/uniffi.toml scripts/make.sh scripts/swift.sh bindings/swift/dev/Package.swift
    sed '/^let releaseChecksum = /d' Package.swift | shasum -a 256
    find crates/ffi/src bindings/swift/Sources build/swift/Arboresce.xcframework -type f -print | LC_ALL=C sort | while IFS= read -r file; do shasum -a 256 "$file"; done
    rustc --version
    swift --version
    xcodebuild -version
}
check_swift_local() {
    [[ -f build/swift/receipt.txt ]] || die 'Swift build receipt missing; run make build-swift'
    cmp -s build/swift/receipt.txt <(swift_inventory) || die 'Swift native build is stale or corrupt; run make build-swift'
}
build_swift_apple() (
    doctor_swift
    generate_swift
    MACOSX_DEPLOYMENT_TARGET=$(sed -nE 's/.*\.macOS\("([^"]+)"\).*/\1/p' Package.swift)
    IPHONEOS_DEPLOYMENT_TARGET=$(sed -nE 's/.*\.iOS\("([^"]+)"\).*/\1/p' Package.swift)
    [[ -n "$MACOSX_DEPLOYMENT_TARGET" && -n "$IPHONEOS_DEPLOYMENT_TARGET" ]] || die 'Missing Apple deployment targets in Package.swift'
    export MACOSX_DEPLOYMENT_TARGET IPHONEOS_DEPLOYMENT_TARGET
    local target
    for target in aarch64-apple-darwin x86_64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios; do
        cargo build --locked --release -p arboresce-ffi --target "$target"
    done
    rm -rf build/swift
    mkdir -p build/swift/include build/swift/macos build/swift/simulator
    cp bindings/swift/Sources/ArboresceBindings/ArboresceNative.h build/swift/include/
    cp bindings/swift/Sources/ArboresceBindings/ArboresceNative.modulemap build/swift/include/module.modulemap
    lipo -create "$(target_dir)/aarch64-apple-darwin/release/libarboresce_ffi.a" "$(target_dir)/x86_64-apple-darwin/release/libarboresce_ffi.a" -output build/swift/macos/libarboresce_ffi.a
    lipo -create "$(target_dir)/aarch64-apple-ios-sim/release/libarboresce_ffi.a" "$(target_dir)/x86_64-apple-ios/release/libarboresce_ffi.a" -output build/swift/simulator/libarboresce_ffi.a
    rm -rf build/swift/Arboresce.xcframework
    xcodebuild -create-xcframework \
      -library "$ROOT/build/swift/macos/libarboresce_ffi.a" -headers "$ROOT/build/swift/include" \
      -library "$ROOT/build/swift/simulator/libarboresce_ffi.a" -headers "$ROOT/build/swift/include" \
      -library "$(target_dir)/aarch64-apple-ios/release/libarboresce_ffi.a" -headers "$ROOT/build/swift/include" \
      -output "$ROOT/build/swift/Arboresce.xcframework"
    swift_inventory > build/swift/receipt.txt
)
build_linux_native() {
    doctor_rust
    require zig
    local target arch
    for target in aarch64-unknown-linux-gnu x86_64-unknown-linux-gnu; do
        build/python/bin/cargo-zigbuild build --locked --release -p arboresce-ffi -p arboresce-node --target "$target.2.17"
        case "$target" in aarch64-*) arch=arm64 ;; x86_64-*) arch=x64 ;; esac
        cp "$(target_dir)/$target/release/libarboresce_node.so" "bindings/typescript/native/arboresce.linux-$arch-gnu.node"
        mkdir -p "build/linux/$target"
        cp "$(target_dir)/$target/release/libarboresce_ffi.so" "build/linux/$target/"
        local jna goarch
        case "$arch" in arm64) jna=aarch64; goarch=arm64 ;; x64) jna=x86-64; goarch=amd64 ;; esac
        mkdir -p "bindings/kotlin/lib/src/main/resources/linux-$jna" "bindings/go/internal/native/lib/linux_$goarch"
        cp "$(target_dir)/$target/release/libarboresce_ffi.so" "bindings/kotlin/lib/src/main/resources/linux-$jna/"
    done
}
build_linux() {
    doctor_python
    build_linux_native
    local target
    for target in aarch64-unknown-linux-gnu x86_64-unknown-linux-gnu; do
        PATH="$ROOT/build/python/bin:$PATH" build/python/bin/maturin build --locked --release --zig --target "$target" --compatibility manylinux2014 --interpreter "$(uv python find --system 3.14.7)" --out build/dist/python
    done
}
test_linux() {
    require docker
    build_linux
    build_typescript
    if [[ $(uname -s) == Darwin ]]; then build_node_all; fi
    package_tool npm-pack
    package_kotlin
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_linux_packages.py -v
}
test_go_platforms() {
    [[ $(uname -s) == Darwin ]] || die 'The complete Go matrix requires macOS, Rosetta, Zig and Docker'
    require docker
    require zig
    build_go_all
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_go_platforms.py -v
}
build_android() {
    doctor_rust
    local ndk_root sdk host ndk
    sdk=${ANDROID_HOME:-$HOME/Library/Android/sdk}
    if [[ $(uname -s) == Linux ]]; then sdk=${ANDROID_HOME:-$HOME/Android/Sdk}; fi
    ndk_root=${ANDROID_NDK_HOME:-}
    if [[ -z "$ndk_root" ]]; then
        for ndk in "$sdk"/ndk/30.* /opt/homebrew/share/android-ndk /usr/local/share/android-ndk; do
            if [[ -f "$ndk/source.properties" ]] && grep -Eq '^Pkg.Revision = 30[.]' "$ndk/source.properties"; then ndk_root=$ndk; break; fi
        done
    fi
    if [[ ! -f "$ndk_root/source.properties" ]] || ! grep -Eq '^Pkg.Revision = 30[.]' "$ndk_root/source.properties"; then
        die 'Install Android NDK r30 in the Android SDK'
    fi
    case $(uname -s) in Darwin) host=darwin-x86_64 ;; Linux) host=linux-x86_64 ;; *) die 'Unsupported Android build host' ;; esac
    ndk="$ndk_root/toolchains/llvm/prebuilt/$host/bin"
    local api alignment
    api=$(sed -nE 's/.*minSdk = ([0-9]+).*/\1/p' bindings/kotlin/android/build.gradle.kts)
    [[ "$api" =~ ^[0-9]+$ ]] || die 'Cannot read Android minSdk from build.gradle.kts'
    alignment=16384
    [[ -x "$ndk/aarch64-linux-android$api-clang" ]] || die 'Android NDK r30 is required'
    export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="$ndk/aarch64-linux-android$api-clang"
    export CARGO_TARGET_ARMV7_LINUX_ANDROIDEABI_LINKER="$ndk/armv7a-linux-androideabi$api-clang"
    export CARGO_TARGET_X86_64_LINUX_ANDROID_LINKER="$ndk/x86_64-linux-android$api-clang"
    local target abi
    for target in aarch64-linux-android armv7-linux-androideabi x86_64-linux-android; do
        case "$target" in
            aarch64-*) abi=arm64-v8a ;;
            armv7-*) abi=armeabi-v7a ;;
            x86_64-*) abi=x86_64 ;;
        esac
        RUSTFLAGS="-C link-arg=-Wl,-z,max-page-size=$alignment" cargo build --locked --release -p arboresce-ffi --target "$target"
        mkdir -p "build/android/jni/$abi"
        cp "$(target_dir)/$target/release/libarboresce_ffi.so" "build/android/jni/$abi/"
        "$ndk/llvm-readelf" -l "build/android/jni/$abi/libarboresce_ffi.so" > "build/android/$abi-elf.txt"
    done
}
build_node_all() {
    build_node
    cargo build --locked --release -p arboresce-node --target x86_64-apple-darwin
    cp "$(target_dir)/x86_64-apple-darwin/release/libarboresce_node.dylib" bindings/typescript/native/arboresce.darwin-x64.node
    build_linux_native
}
build_android_aar() {
    doctor_kotlin
    build_android
    generate_kotlin
    local sdk=${ANDROID_HOME:-$HOME/Library/Android/sdk}
    if [[ $(uname -s) == Linux ]]; then sdk=${ANDROID_HOME:-$HOME/Android/Sdk}; fi
    [[ -d "$sdk/platforms/android-36" ]] || die 'Install Android SDK platform 36 at ~/Library/Android/sdk'
    (cd bindings/kotlin/android && ANDROID_HOME="$sdk" ../gradlew --no-daemon assembleRelease)
}
format() {
    cargo fmt --all
    format_python
    format_typescript
    format_go
    format_kotlin
    format_c
    format_cpp
    if [[ $(uname -s) == Darwin ]]; then format_swift; fi
}
generate() {
    generate_c
    generate_python
    generate_kotlin
    generate_swift
    generate_go
    build_node
    build_wasm
    npm run build --prefix bindings/typescript
}
check_generated() (
    check_generated_c
    verify_go_generator
    build_rust
    doctor_wasm
    mkdir -p build
    verify_node_generator
    local temporary file
    temporary=$(mktemp -d "$ROOT/build/generated-check.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT
    bindgen generate --no-format --library "$(library)" --language python --config crates/ffi/uniffi.toml --out-dir "$temporary/python"
    bindgen generate --no-format --library "$(library)" --language kotlin --config crates/ffi/uniffi.toml --out-dir "$temporary/kotlin"
    bindgen generate --no-format --library "$(library)" --language swift --config crates/ffi/uniffi.toml --out-dir "$temporary/swift"
    build/tools/bin/uniffi-bindgen-go --library "$(library)" --config crates/ffi/uniffi.toml --out-dir "$temporary/go"
    cmp "$temporary/python/arboresce_ffi.py" bindings/python/src/arboresce/arboresce_ffi.py
    cmp "$temporary/kotlin/ai/arboresce/internal/arboresce_ffi.kt" bindings/kotlin/lib/src/main/kotlin/ai/arboresce/internal/arboresce_ffi.kt
    for file in ArboresceBindings.swift ArboresceNative.h ArboresceNative.modulemap; do
        cmp "$temporary/swift/$file" "bindings/swift/Sources/ArboresceBindings/$file"
    done
    for file in arboresce_ffi.go native.h; do
        cmp "$temporary/go/native/$file" "bindings/go/internal/native/$file"
    done
    bindings/typescript/node_modules/.bin/napi build --manifest-path crates/node/Cargo.toml --package-json-path bindings/typescript/package.json --platform --release --output-dir "$temporary/node" --js native.cjs --dts native.d.cts -- --locked
    for file in native.cjs native.d.cts; do
        cmp "$temporary/node/$file" "bindings/typescript/native/$file"
    done
    wasm-pack build crates/wasm --target web --release --out-dir "$temporary/wasm" --out-name arboresce_wasm --locked
    for file in arboresce_wasm.js arboresce_wasm.d.ts arboresce_wasm_bg.wasm.d.ts; do
        cmp "$temporary/wasm/$file" "bindings/typescript/wasm/$file"
    done
    rm -rf "$temporary"
    trap - EXIT
    printf '%s\n' 'Generated bindings match pinned generators'
)
build() {
    build_cpp
    build_python
    build_typescript
    build_kotlin
    build_go
    if [[ $(uname -s) == Darwin ]]; then build_swift; fi
}
test_rust() {
    doctor_rust
    cargo build --locked -p arboresce-ffi --example print-name
    cargo test --locked -p arboresce-ffi
}
test_python() {
    build_python
    uv venv --python "$(uv python find --system 3.14.7)" --no-python-downloads --clear build/consumers/python
    uv pip install --no-cache --python build/consumers/python/bin/python --no-deps --no-index --find-links build/dist/python arboresce==0.0.0
    build/consumers/python/bin/python -I -m unittest discover -s bindings/python/tests -v
    test_python_types
}
compile_typescript_tests() {
    build_typescript
    npm run test:compile --prefix bindings/typescript
}
test_typescript_types() {
    local result
    mkdir -p build
    if (cd bindings/typescript && node node_modules/typescript/bin/tsc --strict --noEmit --module NodeNext --target ES2022 test/types/invalid.ts) > build/typescript-invalid.log 2>&1; then
        die 'TypeScript accepted an invalid consumer type'
    fi
    result=$(grep -c 'error TS' build/typescript-invalid.log)
    if [[ "$result" != 1 ]] || ! grep -q 'TS2322' build/typescript-invalid.log; then
        die 'Unexpected TypeScript consumer failure; see build/typescript-invalid.log'
    fi
}
test_node() {
    compile_typescript_tests
    (cd bindings/typescript && node --test build/test/node.test.js)
    test_typescript_types
}
test_wasm() {
    compile_typescript_tests
    (cd bindings/typescript && node --test build/test/wasm.test.js)
}
setup_browser() {
    setup_typescript
    if [[ $(uname -s) == Linux ]]; then
        bindings/typescript/node_modules/.bin/playwright install --with-deps chromium
    else
        bindings/typescript/node_modules/.bin/playwright install chromium
    fi
}
test_browser() {
    build_typescript
    npm run test:browser --prefix bindings/typescript
}
test_go() {
    build_go
    (cd bindings/go && go test -race -count=1 -v ./...)
}
test_kotlin() {
    build_kotlin
    (cd bindings/kotlin && ./gradlew --no-daemon :lib:test :lib:copyRuntimeDependencies)
}
test_swift() {
    build_swift
    swift test --package-path build/swift-dev
}
test_ios() {
    build_swift_apple
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_ios.py -v
}
test_swift_platforms() {
    build_swift_apple
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_swift_platforms.py -v
}
test_android() {
    build_android_aar
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_android.py -v
}
test_all() {
    test_c
    test_cpp
    test_rust
    test_python
    test_node
    test_wasm
    test_kotlin
    test_go
    if [[ $(uname -s) == Darwin ]]; then test_swift; fi
}
check_rust() {
    cargo fmt --all -- --check
    cargo clippy --locked --workspace --all-targets -- -D warnings
}
check() {
    check_rust
    shellcheck scripts/*.sh
    check_python
    check_typescript
    check_go
    check_kotlin
    check_c
    check_cpp
    check_support
    if [[ $(uname -s) == Darwin ]]; then check_swift; fi
}
help() {
    printf '%s\n' 'make setup-checks: install pinned handwritten-source format/type tools' \
      'make check-<language> | format-<language>: rust, python, typescript, kotlin, go, swift, c, cpp' \
      'make package-python | package-typescript | package-kotlin | package-android | package-go | package-swift | package-c | package-cpp' \
      'make test-typescript-consumer | test-browser-consumer | test-kotlin-consumer | test-go-consumer | test-swift-consumer | test-c-consumer | test-cpp-consumer' \
      'make update-support | check-support: public intended target metadata' \
      'make test-c-static | test-c-shared | test-c-abi | test-cpp-no-exceptions'
    printf '%s\n' 'make test-go-platforms: build and test the complete Go platform matrix'
    printf '%s\n' 'Per-language commands: make setup-<language>, make doctor-<language>' 'Languages: rust, python, typescript, kotlin, go, swift'
    printf '%s\n' 'make test-rust' 'make setup-browser' 'make test-browser' 'make test-ios' 'make test-android' 'make test-swift-platforms'
    printf '%s\n' 'Arboresce SDK developer commands' '' \
      '  make doctor             Check installed toolchains' \
      '  make setup              Prepare pinned build dependencies' \
      '  make generate           Generate all UniFFI bindings' \
      '  make build              Build all SDKs for this host' \
      '  make build-rust         Build the Rust FFI library and generator' \
      '  make build-python       Build native Python wheels' \
      '  make build-typescript   Build Node, browser WASM and TypeScript' \
      '  make build-node         Build the Node native addon' \
      '  make build-node-all     Build macOS/Linux Node platform packages' \
      '  make build-android-aar  Build the Android AAR using the Android SDK' \
      '  make build-wasm         Build browser WASM bindings' \
      '  make build-kotlin       Build the JVM package' \
      '  make build-swift        Build Swift and its native library' \
      '  make check-swift-local  Reject stale or altered Swift binaries' \
      '  make build-go           Build generated Go bindings' \
      '  make build-go-all       Build the complete Go native matrix' \
      '  make setup-go           Install/repair the pinned Go generator' \
      '  make doctor-go          Check Go generator, CGO and platform' \
      '  make check-go-generator Verify generator version and revision' \
      '  make build-swift-apple   Build five Apple native slices' \
      '  make build-android       Build three Android native ABIs' \
      '  make build-linux         Build Linux arm64/x86_64 libraries and wheels' \
      '  make test-linux          Run Linux Node/Python/JVM consumers in Docker' \
      '  make test                Build and run host regression suites' \
      '  make format              Format Rust and handwritten Go' \
      '  make check-generated     Compare regenerated UniFFI sources' \
      '  make check              Check all Rust adapters' \
      '  make verify             Lint, check generation and run host regression suites' \
      '  make generate-python | generate-kotlin | generate-swift | generate-go' \
      '  make test-python | test-node | test-wasm | test-kotlin | test-go | test-swift'
}
# shellcheck source=scripts/checks.sh
source "$ROOT/scripts/checks.sh"
# shellcheck source=scripts/native.sh
source "$ROOT/scripts/native.sh"
# shellcheck source=scripts/packages.sh
source "$ROOT/scripts/packages.sh"
# shellcheck source=scripts/swift.sh
source "$ROOT/scripts/swift.sh"
# shellcheck source=scripts/support.sh
source "$ROOT/scripts/support.sh"

[[ $# == 1 ]] || die 'Expected exactly one fixed command; run make help'
case "$1" in
    test-tooling) uv run --python 3.14.7 --no-project python -m unittest discover -s tests/consumers -p "test_*.py" -v; uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_mobile_helpers.py -v; uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_targets.py -v ;;
    package-c) package_c ;;
    package-cpp) package_cpp ;;
    test-c-package) test_c_package ;;
    test-cpp-package) test_cpp_package ;;
    package-python) build_python ;;
    package-swift) package_swift ;;
    test-swift-consumer) test_swift_consumer ;;
    build-kotlin-all) build_kotlin_all ;;
    check-rust) check_rust ;;
    setup-checks) setup_checks ;;
    setup-c) setup_c ;;
    setup-cpp) setup_cpp ;;
    doctor-c) doctor_c ;;
    doctor-cpp) doctor_cpp ;;
    generate-c) generate_c ;;
    check-generated-c) check_generated_c ;;
    build-c) build_c ;;
    build-cpp) build_cpp ;;
    install-c) install_c ;;
    test-c) test_c ;;
    test-c-static) test_c_static ;;
    test-c-shared) test_c_shared ;;
    test-c-abi) test_c_abi ;;
    test-c-consumer) test_c_consumer ;;
    test-cpp) test_cpp ;;
    test-cpp-consumer) test_cpp_consumer ;;
    test-cpp-no-exceptions) test_cpp_no_exceptions ;;
    package-typescript) package_typescript ;;
    package-typescript-all) package_typescript_all ;;
    package-go) package_go ;;
    package-kotlin) package_kotlin ;;
    package-kotlin-all) package_kotlin_all ;;
    package-android) package_android ;;
    test-typescript-consumer) test_typescript_consumer ;;
    test-browser-consumer) test_browser_consumer ;;
    test-go-consumer) test_go_consumer ;;
    test-kotlin-consumer) test_kotlin_consumer ;;
    test-python-types) test_python_types ;;
    stage-swift-dev) stage_swift_dev ;;
    check-support) check_support ;;
    update-support) update_support ;;
    check-python) check_python ;;
    format-python) format_python ;;
    check-typescript) check_typescript ;;
    format-typescript) format_typescript ;;
    check-go) check_go ;;
    format-go) format_go ;;
    check-kotlin) check_kotlin ;;
    format-kotlin) format_kotlin ;;
    check-swift) check_swift ;;
    format-swift) format_swift ;;
    check-c) check_c ;;
    format-c) format_c ;;
    check-cpp) check_cpp ;;
    format-cpp) format_cpp ;;
    help) help ;;
    doctor) doctor ;;
    setup) setup ;;
    setup-rust) setup_rust ;;
    setup-python) setup_python ;;
    setup-typescript) setup_typescript ;;
    setup-kotlin) setup_kotlin ;;
    setup-swift) setup_swift ;;
    doctor-rust) doctor_rust ;;
    doctor-python) doctor_python ;;
    doctor-typescript) doctor_typescript ;;
    doctor-kotlin) doctor_kotlin ;;
    doctor-swift) doctor_swift ;;
    setup-go) setup_go_generator ;;
    doctor-go) doctor_go ;;
    check-go-generator) verify_go_generator ;;
    build-go-all) build_go_all ;;
    setup-apple) rustup target add aarch64-apple-darwin x86_64-apple-darwin aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios ;;
    setup-android) rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android ;;
    setup-linux) setup_python; rustup target add aarch64-unknown-linux-gnu x86_64-unknown-linux-gnu ;;
    generate) generate ;;
    check-generated) check_generated ;;
    generate-python) generate_python ;;
    generate-kotlin) generate_kotlin ;;
    generate-swift) generate_swift ;;
    generate-go) generate_go ;;
    build) build ;;
    build-rust) build_rust ;;
    build-python) build_python ;;
    build-typescript) build_typescript ;;
    build-node) build_node ;;
    build-node-all) build_node_all ;;
    build-android-aar) build_android_aar ;;
    build-wasm) build_wasm ;;
    build-kotlin) build_kotlin ;;
    build-swift) build_swift ;;
    check-swift-local) check_swift_local ;;
    build-go) build_go ;;
    test-rust) test_rust ;;
    setup-browser) setup_browser ;;
    test-browser) test_browser ;;
    test-ios) test_ios ;;
    test-android) test_android ;;
    test-swift-platforms) test_swift_platforms ;;
    test) test_all ;;
    test-python) test_python ;;
    test-node) test_node ;;
    test-wasm) test_wasm ;;
    test-kotlin) test_kotlin ;;
    test-go) test_go ;;
    test-swift) test_swift ;;
    build-swift-apple) build_swift_apple ;;
    build-android) build_android ;;
    build-linux) build_linux ;;
    test-linux) test_linux ;;
    test-go-platforms) test_go_platforms ;;
    format) format ;;
    verify) doctor; check; check_generated; test_all ;;
    check) check ;;
    *) die "Unknown command: $1" ;;
esac
