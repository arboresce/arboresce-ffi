import ArboresceBindings

public enum Arboresce {
  public static var name: String { ArboresceBindings.name() }

  public static func projectName() -> String {
    ArboresceBindings.name()
  }

  public static func printName() {
    ArboresceBindings.printName()
  }
}
