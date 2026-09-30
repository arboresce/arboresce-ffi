// swift-tools-version: 6.3
import PackageDescription

let releaseTag = "0.0.0"
let releaseChecksum = "fba591a4c5744460f1e2dbef0c15484ba78e5e6e68a05b0ac12760c40ebb75b1"

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
