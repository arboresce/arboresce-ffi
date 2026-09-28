#!/usr/bin/env bash

rust_flags() {
    local encoded=${CARGO_ENCODED_RUSTFLAGS-} flag
    for flag in "$@"; do
        if [[ -n "$encoded" ]]; then encoded+=$'\x1f'; fi
        encoded+=$flag
    done
    printf '%s' "$encoded"
}

prepare_rust_flags() {
    local flag prefix mapped encoded='' source
    if [[ ! ${CARGO_ENCODED_RUSTFLAGS+x} ]]; then
        encoded=$(
            set -f
            IFS=$' \t\n\r\v\f'
            for flag in ${RUSTFLAGS-}; do
                if [[ -n "$encoded" ]]; then encoded+=$'\x1f'; fi
                encoded+=$flag
            done
            printf '%s' "$encoded"
        )
        export CARGO_ENCODED_RUSTFLAGS=$encoded
    fi
    for source in user sdk cargo rustup target; do
        case "$source" in
            user) prefix=$HOME; mapped=/build/user ;;
            cargo) prefix=${CARGO_HOME:-$HOME/.cargo}; mapped=/cargo ;;
            rustup) prefix=${RUSTUP_HOME:-$HOME/.rustup}; mapped=/rustup ;;
            target) prefix=${CARGO_TARGET_DIR:-$ROOT/target}; mapped=/build/target ;;
            sdk) prefix=$ROOT; mapped=/src/arboresce-ffi ;;
        esac
        [[ "$prefix" == /* ]] || prefix="$ROOT/$prefix"
        CARGO_ENCODED_RUSTFLAGS=$(rust_flags "--remap-path-prefix=$prefix=$mapped")
        if [[ -d "$prefix" ]]; then
            prefix=$(cd "$prefix" && pwd -P)
            CARGO_ENCODED_RUSTFLAGS=$(rust_flags "--remap-path-prefix=$prefix=$mapped")
        fi
    done
    export CARGO_ENCODED_RUSTFLAGS
}
