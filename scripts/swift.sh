#!/usr/bin/env bash

stage_swift_dev() (
    check_swift_local
    local destination="$ROOT/build/swift-dev" temporary item
    [[ ! -L "$destination" ]] || die 'Swift staging directory cannot be a symlink'
    temporary=$(mktemp -d "$ROOT/build/swift-stage.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT
    cp "$ROOT/bindings/swift/dev/Package.swift" "$temporary/Package.swift"
    cp -R "$ROOT/bindings/swift/Sources" "$ROOT/bindings/swift/Tests" "$temporary/"
    cp -R "$ROOT/build/swift/Arboresce.xcframework" "$temporary/"
    cp "$ROOT/bindings/swift/README.md" "$ROOT/LICENSE-MIT" "$ROOT/LICENSE-APACHE" "$temporary/"
    mkdir -p "$destination"
    for item in Package.swift Sources Tests Arboresce.xcframework README.md LICENSE-MIT LICENSE-APACHE; do
        rm -rf "${destination:?}/${item:?}"
        mv "$temporary/$item" "$destination/$item"
    done
)

package_swift() {
    build_swift_apple
    stage_swift_dev
    require uv
    uv run --python 3.14.7 --no-project python tests/consumers/swift_packages.py package
}

test_swift_consumer() {
    package_swift
    uv run --python 3.14.7 --no-project python tests/consumers/swift_packages.py test
}
