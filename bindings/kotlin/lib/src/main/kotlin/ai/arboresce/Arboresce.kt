package ai.arboresce

object Arboresce {
    @JvmField val NAME: String = ai.arboresce.internal.name()

    @JvmStatic fun name(): String = ai.arboresce.internal.name()

    @JvmStatic
    fun printName() {
        ai.arboresce.internal.printName()
    }
}
