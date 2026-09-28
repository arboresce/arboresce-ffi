#!/usr/bin/env bash

doctor_c_tools() {
    doctor_rust
    require cc; require cmake; require pkg-config; require uv
    cmake -E capabilities | jq -e '.version | (.major > 3 or (.major == 3 and .minor >= 24))' >/dev/null || die 'CMake 3.24 or newer is required'
    case $(uname -s) in Darwin) require otool; require nm ;; Linux) require readelf; require nm ;; *) die 'Native C packaging currently targets macOS and Linux' ;; esac
}
doctor_c() {
    doctor_c_tools
    [[ -x build/tools/bin/cbindgen ]] && [[ $(build/tools/bin/cbindgen --version) == 'cbindgen 0.29.4' ]] || die 'Run make setup-c for cbindgen 0.29.4'
}
setup_c() {
    doctor_c_tools
    if [[ ! -x build/tools/bin/cbindgen ]] || [[ $(build/tools/bin/cbindgen --version) != 'cbindgen 0.29.4' ]]; then
        cargo install cbindgen --version 0.29.4 --locked --root build/tools
    fi
}
doctor_cpp() { doctor_c; require c++; }
setup_cpp() { setup_c; require c++; }
generate_c() {
    doctor_c
    emit_c_header bindings/c/include/arboresce/arboresce.h
}
emit_c_header() (
    mkdir -p build
    local metadata
    metadata=$(mktemp "$ROOT/build/c-metadata.XXXXXX")
    trap 'rm -f "$metadata"' EXIT
    cargo metadata --locked --no-deps --format-version 1 > "$metadata"
    build/tools/bin/cbindgen --config crates/c/cbindgen.toml --crate arboresce-c --lockfile Cargo.lock --metadata "$metadata" --output "$1"
)
check_generated_c() (
    doctor_c
    mkdir -p build
    local temporary
    temporary=$(mktemp "$ROOT/build/c-header.XXXXXX")
    trap 'rm -f "$temporary"' EXIT
    emit_c_header "$temporary"
    cmp "$temporary" bindings/c/include/arboresce/arboresce.h
)
build_c() {
    doctor_c
    check_generated_c
    mkdir -p build/native/stage
    local artifacts version host
    host=$(rustc -vV | sed -n 's/^host: //p')
    [[ -n "$host" ]] || die 'Rust did not report its host target'
    CARGO_PROFILE_C_RELEASE_PANIC=unwind CARGO_ENCODED_RUSTFLAGS="$(rust_flags -Crelocation-model=pic -Cpanic=unwind)" cargo rustc --locked --target "$host" --profile c-release -p arboresce-c --lib -- --print native-static-libs > build/native/build.log 2>&1 || { cat build/native/build.log >&2; return 1; }
    cat build/native/build.log
    sed -n 's/^note: native-static-libs: //p' build/native/build.log | tail -1 > build/native/stage/native-static-libs.txt
    [[ -s build/native/stage/native-static-libs.txt ]] || die 'Rust did not report the native static dependencies'
    artifacts="$(target_dir)/$host/c-release"
    cp "$artifacts/libarboresce_c.a" build/native/stage/
    case $(uname -s) in
        Darwin)
            xcrun strip -S build/native/stage/libarboresce_c.a
            cp "$artifacts/libarboresce_c.dylib" build/native/stage/libarboresce_c.1.dylib
            ln -sf libarboresce_c.1.dylib build/native/stage/libarboresce_c.dylib
            ;;
        Linux)
            cp "$artifacts/libarboresce_c.so" build/native/stage/libarboresce_c.so.1
            ln -sf libarboresce_c.so.1 build/native/stage/libarboresce_c.so
            ;;
    esac
    version=$(cargo metadata --locked --no-deps --format-version 1 | jq -r '.packages[] | select(.name == "arboresce-c") | .version')
    cmake -S bindings/c -B build/native/c -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_LIBDIR=lib -DARBORESCE_NATIVE_DIR="$ROOT/build/native/stage" -DARBORESCE_VERSION="$version" -DCMAKE_INSTALL_PREFIX="$ROOT/build/native/install"
    cmake --build build/native/c --parallel
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py record-build
}
install_c() { build_c; cmake --install build/native/c; }
test_c_abi() {
    build_c
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k NativeAbi -v
}
test_c_static() { build_c; ctest --test-dir build/native/c --output-on-failure -R '_static$'; }
test_c_shared() { build_c; ctest --test-dir build/native/c --output-on-failure -R '_shared$'; }
test_c_consumer() {
    install_c
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k CConsumers -v
}
test_c() {
    cargo test --locked -p arboresce-c
    install_c
    ctest --test-dir build/native/c --output-on-failure
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k NativeAbi -v
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k CConsumers -v
}
build_cpp() {
    doctor_cpp
    install_c
    local version
    version=$(cargo metadata --locked --no-deps --format-version 1 | jq -r '.packages[] | select(.name == "arboresce-c") | .version')
    cmake -S bindings/cpp -B build/native/cpp -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_PREFIX_PATH="$ROOT/build/native/install" -DCMAKE_INSTALL_PREFIX="$ROOT/build/native/install" -DARBORESCE_VERSION="$version"
    cmake --build build/native/cpp --parallel
    cmake --install build/native/cpp
}
test_cpp_no_exceptions() { build_cpp; ctest --test-dir build/native/cpp --output-on-failure -R no_exceptions; }
test_cpp_consumer() {
    build_cpp
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k CppConsumers -v
}
test_cpp() {
    build_cpp
    ctest --test-dir build/native/cpp --output-on-failure
    uv run --python 3.14.7 --no-project python -m unittest discover -s tests/platforms -p test_c_cpp.py -k CppConsumers -v
}
package_c() {
    install_c
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py package-c
}
package_cpp() {
    build_cpp
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py package-c
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py package-cpp
}
test_c_package() {
    package_c
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py test-c-package
}
test_cpp_package() {
    package_cpp
    uv run --python 3.14.7 --no-project python tests/consumers/native_packages.py test-cpp-package
}
