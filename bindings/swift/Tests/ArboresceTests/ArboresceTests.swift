import Arboresce
import Foundation
import XCTest

@MainActor
final class ArboresceTests: XCTestCase {
  func testIdentity() {
    XCTAssertEqual(Arboresce.name, "Arboresce")
    XCTAssertEqual(Arboresce.projectName(), "Arboresce")
  }

  func testRepeatedCalls() {
    for _ in 0..<1000 {
      XCTAssertEqual(Arboresce.projectName(), "Arboresce")
    }
  }

  func testConcurrentCalls() async {
    await withTaskGroup(of: Bool.self) { group in
      for _ in 0..<8 {
        group.addTask {
          (0..<128).allSatisfy { _ in Arboresce.projectName() == "Arboresce" }
        }
      }
      for await valid in group {
        XCTAssertTrue(valid)
      }
    }
  }

  #if os(macOS)
    func testPrintName() throws {
      let process = Process()
      process.executableURL = Bundle(for: ArboresceTests.self).bundleURL.deletingLastPathComponent()
        .appendingPathComponent("PrintName")
      let output = Pipe()
      process.standardOutput = output
      try process.run()
      process.waitUntilExit()
      XCTAssertEqual(process.terminationStatus, 0)
      XCTAssertEqual(
        String(decoding: output.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self),
        "Arboresce\n")
    }
  #endif
}
