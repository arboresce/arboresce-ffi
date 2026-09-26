package ai.arboresce.consumer

import ai.arboresce.Arboresce
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ArboresceTest {
    @Test
    fun identity() {
        assertEquals("Arboresce", Arboresce.NAME)
        assertEquals("Arboresce", Arboresce.name())
    }

    @Test
    fun repeatedCalls() {
        repeat(1000) { assertEquals("Arboresce", Arboresce.name()) }
    }

    @Test
    fun concurrentCalls() {
        val executor = Executors.newFixedThreadPool(8)
        try {
            val tasks =
                List(8) { Callable { repeat(128) { assertEquals("Arboresce", Arboresce.name()) } } }
            executor.invokeAll(tasks, 20, TimeUnit.SECONDS).forEach { it.get() }
        } finally {
            executor.shutdownNow()
        }
    }

    @Test
    fun printName() {
        val process =
            ProcessBuilder(
                    "${System.getProperty("java.home")}/bin/java",
                    "-cp",
                    System.getProperty("arboresce.consumer.classpath"),
                    "ai.arboresce.consumer.PrintNameKt",
                )
                .start()
        try {
            assertTrue(process.waitFor(20, TimeUnit.SECONDS))
            assertEquals(0, process.exitValue(), process.errorStream.bufferedReader().readText())
            assertEquals("Arboresce\n", process.inputStream.bufferedReader().readText())
        } finally {
            process.destroyForcibly()
        }
    }
}
