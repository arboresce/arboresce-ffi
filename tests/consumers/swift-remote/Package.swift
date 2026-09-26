// swift-tools-version: 6.3
import PackageDescription

let package = Package(
  name: "Consumer",
  platforms: [.macOS("11.0")],
  dependencies: [
    .package(url: "https://github.com/arboresce/arboresce-ffi.git", exact: "0.0.0")
  ],
  targets: [
    .executableTarget(
      name: "Consumer", dependencies: [.product(name: "Arboresce", package: "arboresce-ffi")])
  ]
)
