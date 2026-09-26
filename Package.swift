// swift-tools-version: 6.3
import PackageDescription

let releaseTag = "0.0.0"
let releaseChecksum = "e4f8204d2af86756b350c12c926448002c3862960c90ddb602ae190f7bd9a749"

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
