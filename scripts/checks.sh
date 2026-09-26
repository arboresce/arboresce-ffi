#!/usr/bin/env bash

setup_checks() {
    require uv; require curl
    UV_PROJECT_ENVIRONMENT=build/checks uv sync --locked --only-group checks --no-install-project --python 3.14.7
    mkdir -p build/tools
    local jar=build/tools/ktfmt-0.58.jar
    if [[ ! -f "$jar" ]] || ! verify_ktfmt >/dev/null 2>&1; then
        curl --fail --location --silent --show-error https://repo.maven.apache.org/maven2/com/facebook/ktfmt/0.58/ktfmt-0.58-with-dependencies.jar --output "$jar"
    fi
    verify_ktfmt
}
verify_ktfmt() {
    [[ $(shasum -a 256 build/tools/ktfmt-0.58.jar | cut -d ' ' -f 1) == 0369a4351367b0de2374b0f1c3962ef7d5d222a4bc58d7197d06948d46e4bea5 ]]
}
check_tools() {
    [[ -x build/checks/bin/ruff && -x build/checks/bin/mypy && -x build/checks/bin/clang-format ]] || die 'Run make setup-checks first'
}
python_files() {
    find bindings/python tests -type d \( -name build -o -name __pycache__ -o -name .gradle -o -name .kotlin \) -prune -o -type f \( -name '*.py' -o -name '*.pyi' \) ! -name arboresce_ffi.py -print
}
format_python() {
    check_tools
    local files=() file
    while IFS= read -r file; do files+=("$file"); done < <(python_files)
    build/checks/bin/ruff check --cache-dir build/ruff --fix "${files[@]}"
    build/checks/bin/ruff format --cache-dir build/ruff "${files[@]}"
}
check_python() {
    check_tools
    local files=() file
    while IFS= read -r file; do files+=("$file"); done < <(python_files)
    build/checks/bin/ruff check --cache-dir build/ruff "${files[@]}"
    build/checks/bin/ruff format --cache-dir build/ruff --check "${files[@]}"
}
test_python_types() {
    check_tools
    uv run --python 3.14.7 --no-project python tests/consumers/python_types.py build/consumers/python/bin/python
}
typescript_format() {
    doctor_typescript
    bindings/typescript/node_modules/.bin/prettier "$1" 'bindings/typescript/src/**/*.{ts,mjs}' 'bindings/typescript/test/**/*.{ts,mjs}' 'tests/consumers/typescript/*.mjs' 'tests/platforms/fixtures/node/*.mjs' --ignore-unknown
}
format_typescript() { typescript_format --write; }
check_typescript() {
    typescript_format --check
    (cd bindings/typescript && node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json)
}
go_files() {
    find bindings/go -type f -name '*.go' ! -name arboresce_ffi.go
}
format_go() { go_files | while IFS= read -r file; do gofmt -w "$file"; done; }
check_go() {
    local file
    while IFS= read -r file; do [[ -z $(gofmt -l "$file") ]] || die "Go formatting differs: $file"; done < <(go_files)
    (cd bindings/go && go vet ./...)
}
kotlin_format() {
    doctor_kotlin
    verify_ktfmt || die 'Run make setup-checks to install the pinned Kotlin formatter'
    local files=() file
    while IFS= read -r file; do files+=("$file"); done < <(find bindings/kotlin tests -type d \( -name build -o -name .gradle -o -name .kotlin \) -prune -o -type f \( -name '*.kt' -o -name '*.kts' \) ! -name arboresce_ffi.kt -print)
    java -jar build/tools/ktfmt-0.58.jar --kotlinlang-style "$@" "${files[@]}"
}
format_kotlin() { kotlin_format; }
check_kotlin() { kotlin_format --dry-run --set-exit-if-changed; }
swift_format() {
    doctor_swift
    local files=(Package.swift) file
    while IFS= read -r file; do files+=("$file"); done < <(find bindings/swift tests/consumers/swift tests/consumers/swift-remote -type f -name '*.swift' ! -path '*/ArboresceBindings/*')
    swift format "$@" "${files[@]}"
}
format_swift() { swift_format --in-place; }
check_swift() { swift_format lint --strict; }
native_format() {
    check_tools
    local files=() file
    while IFS= read -r file; do files+=("$file"); done < <(find "bindings/$1" -type f \( -name '*.h' -o -name '*.hpp' -o -name '*.c' -o -name '*.cpp' \) ! -name arboresce.h)
    shift
    build/checks/bin/clang-format "$@" "${files[@]}"
}
format_c() { native_format c -i; }
format_cpp() { native_format cpp -i; }
check_c() { native_format c --dry-run --Werror; }
check_cpp() { native_format cpp --dry-run --Werror; }
