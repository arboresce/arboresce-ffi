plugins { kotlin("jvm") version "2.2.0" }

repositories {
    exclusiveContent {
        forRepository { maven { url = uri("../maven") } }
        filter { includeGroup("ai.arboresce") }
    }
    mavenCentral()
}

kotlin { jvmToolchain(21) }

dependencies {
    implementation("ai.arboresce:arboresce:0.0.0")
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.10.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.1")
}

tasks.register("verifyCompileClasspath") {
    doLast {
        check(configurations.compileClasspath.get().none { it.name.startsWith("jna-") }) {
            "JNA must be a runtime dependency of the public facade"
        }
    }
}

tasks.register<Copy>("copyRuntimeDependencies") {
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir("runtime"))
}

tasks.test {
    dependsOn("verifyCompileClasspath")
    useJUnitPlatform()
    systemProperty("arboresce.consumer.classpath", sourceSets.test.get().runtimeClasspath.asPath)
    testLogging { events("passed", "skipped", "failed") }
}
