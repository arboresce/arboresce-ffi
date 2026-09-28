// swift-tools-version: 6.3
import PackageDescription

let releaseTag = "0.0.0"
let releaseChecksum = "ac5ce97d8bfdcf21fdcc1ef09bf1a21bea6f975d4a3f3c8c97025557b837736f"

let package = Package(
  name: "Arboresce",
  platforms: [.macOS("11.0"), .iOS("13.0")],
  products: [
    .library(name: "Arboresce", targets: ["Arboresce"])
  ],
  targets: [
    .binaryTarget(
      name: "ArboresceNative",
      url:
        "https://github.com/arboresce/arboresce-ffi/releases/download/\(releaseTag)/Arboresce.xcframework.zip",
      checksum: releaseChecksum),
    .executableTarget(
      name: "PrintName", dependencies: ["Arboresce"],
      path: "bindings/swift/Tests/Fixtures/PrintName"),
    .testTarget(
      name: "ArboresceTests", dependencies: ["Arboresce", "PrintName"],
      path: "bindings/swift/Tests/ArboresceTests"),
    .target(
      name: "ArboresceBindings", dependencies: ["ArboresceNative"],
      path: "bindings/swift/Sources/ArboresceBindings", sources: ["ArboresceBindings.swift"]),
    .target(
      name: "Arboresce", dependencies: ["ArboresceBindings"],
      path: "bindings/swift/Sources/Arboresce"),
  ]
)
