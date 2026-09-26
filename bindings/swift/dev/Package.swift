// swift-tools-version: 6.3
import PackageDescription

let package = Package(
  name: "Arboresce",
  platforms: [.macOS("11.0"), .iOS("13.0")],
  products: [
    .library(name: "Arboresce", targets: ["Arboresce"])
  ],
  targets: [
    .binaryTarget(name: "ArboresceNative", path: "Arboresce.xcframework"),
    .executableTarget(
      name: "PrintName", dependencies: ["Arboresce"], path: "Tests/Fixtures/PrintName"),
    .testTarget(
      name: "ArboresceTests", dependencies: ["Arboresce", "PrintName"], path: "Tests/ArboresceTests"
    ),
    .target(
      name: "ArboresceBindings", dependencies: ["ArboresceNative"],
      path: "Sources/ArboresceBindings", sources: ["ArboresceBindings.swift"]),
    .target(name: "Arboresce", dependencies: ["ArboresceBindings"], path: "Sources/Arboresce"),
  ]
)
