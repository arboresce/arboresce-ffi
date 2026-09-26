// swift-tools-version: 6.3
import PackageDescription

let package = Package(
  name: "ArboresceConsumerTests",
  platforms: [.macOS("11.0"), .iOS("13.0")],
  dependencies: [.package(name: "arboresce-ffi", path: "../package")],
  targets: [
    .executableTarget(
      name: "PrintName", dependencies: [.product(name: "Arboresce", package: "arboresce-ffi")]),
    .testTarget(
      name: "ArboresceTests", dependencies: [.product(name: "Arboresce", package: "arboresce-ffi")]),
  ]
)
