def swift_package_paths(package):
    if (package / "Sources").is_dir():
        sources = package / "Sources"
        framework = package / "Arboresce.xcframework"
    else:
        sources = package / "bindings/swift/Sources"
        framework = package / "build/swift/Arboresce.xcframework"
    if not sources.is_dir() or not (framework / "Info.plist").is_file():
        raise ValueError(f"Missing Swift package sources or XCFramework in {package}")
    return sources, framework
