#!/usr/bin/env bash
set -euo pipefail

ROOT=$1
NATIVE_SOURCE=$2
HOST=$3
TARGET_ROOT="$ROOT/target"
mkdir -p "$TARGET_ROOT/c-release"
for artifact in libarboresce_c.a libarboresce_c.dylib libarboresce_c.so; do
    printf 'stale host artifact' > "$TARGET_ROOT/c-release/$artifact"
done
cd "$ROOT"

target_dir() { printf '%s\n' "$TARGET_ROOT"; }
die() { printf '%s\n' "$*" >&2; exit 1; }
rustc() { printf 'rustc fixture\nhost: %s\n' "$HOST"; }
cmake() { :; }
uv() { :; }
cargo() {
    local target artifact
    case "$1" in
        metadata)
            printf '{"packages":[{"name":"arboresce-c","version":"0.0.0"}]}\n'
            ;;
        rustc)
            target=${CARGO_BUILD_TARGET:-$HOST}
            while [[ $# -gt 0 ]]; do
                if [[ "$1" == --target ]]; then
                    target=$2
                    shift
                fi
                shift
            done
            printf '%s\n' "$target" > "$ROOT/selected-target"
            mkdir -p "$TARGET_ROOT/$target/c-release"
            for artifact in libarboresce_c.a libarboresce_c.dylib libarboresce_c.so; do
                printf 'fresh explicit host artifact' > "$TARGET_ROOT/$target/c-release/$artifact"
            done
            printf 'note: native-static-libs: -lc -lm\n' >&2
            ;;
        *) return 1 ;;
    esac
}

# shellcheck source=scripts/native.sh
source "$NATIVE_SOURCE"
doctor_c() { :; }
check_generated_c() { :; }
build_c
