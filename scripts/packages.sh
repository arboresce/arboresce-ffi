#!/usr/bin/env bash

package_tool() {
    require uv
    uv run --python 3.14.7 --no-project python tests/consumers/package_tools.py "$@"
}
package_typescript() {
    build_typescript
    package_tool npm-pack
}
package_typescript_all() {
    [[ $(uname -s) == Darwin ]] || die 'The complete npm matrix requires macOS and Zig'
    build_typescript
    build_node_all
    package_tool npm-pack
}
test_typescript_consumer() {
    package_typescript
    package_tool npm-test
}
test_browser_consumer() {
    package_typescript
    package_tool npm-browser-test
}
package_go() {
    doctor_go
    build_go_all
    package_tool go-pack
}
test_go_consumer() {
    package_go
    package_tool go-test
}
package_kotlin() {
    build_kotlin
    publish_kotlin_package
}
publish_kotlin_package() {
    (cd bindings/kotlin && ./gradlew --no-daemon :lib:publishSdkPublicationToLocalRepository)
    package_tool maven-check
}
build_kotlin_all() {
    [[ $(uname -s) == Darwin ]] || die 'The complete JVM matrix requires macOS and Zig'
    build_linux_native
    local target platform
    for target in aarch64-apple-darwin x86_64-apple-darwin; do
        cargo build --locked --release -p arboresce-ffi --target "$target"
        case "$target" in aarch64-*) platform=darwin-aarch64 ;; x86_64-*) platform=darwin-x86-64 ;; esac
        mkdir -p "bindings/kotlin/lib/src/main/resources/$platform"
        cp "$(target_dir)/$target/release/libarboresce_ffi.dylib" "bindings/kotlin/lib/src/main/resources/$platform/"
    done
    build_kotlin
}
package_kotlin_all() {
    build_kotlin_all
    publish_kotlin_package
}
test_kotlin_consumer() {
    package_kotlin
    package_tool kotlin-test
}
package_android() {
    package_kotlin
    build_android_aar
    local sdk=${ANDROID_HOME:-$HOME/Library/Android/sdk}
    if [[ $(uname -s) == Linux ]]; then sdk=${ANDROID_HOME:-$HOME/Android/Sdk}; fi
    (cd bindings/kotlin/android && ANDROID_HOME="$sdk" ../gradlew --no-daemon publishAndroidPublicationToLocalRepository)
    package_tool android-check
}
