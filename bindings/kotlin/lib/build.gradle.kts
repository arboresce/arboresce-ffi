import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("jvm")
    `java-library`
    `maven-publish`
    id("org.jetbrains.dokka")
}

group = rootProject.group

version = rootProject.version

base { archivesName.set("arboresce") }

description = "Kotlin SDK for Arboresce."

repositories { mavenCentral() }

dependencies { implementation("net.java.dev.jna:jna:5.17.0") }

kotlin {
    jvmToolchain(21)
    compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
}

java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
    withSourcesJar()
}

tasks.withType<Jar>().configureEach {
    from(rootProject.files("LICENSE-MIT", "LICENSE-APACHE")) { into("META-INF") }
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

val apiDocsJar by
    tasks.registering(Jar::class) {
        archiveClassifier.set("javadoc")
        from(tasks.dokkaGeneratePublicationHtml.flatMap { it.outputDirectory })
    }

publishing {
    publications {
        create<MavenPublication>("sdk") {
            artifactId = "arboresce"
            from(components["java"])
            artifact(apiDocsJar)
            pom {
                name.set("Arboresce")
                description.set(project.description)
                url.set("https://arboresce.ai")
                licenses {
                    license {
                        name.set("MIT")
                        url.set("https://opensource.org/license/mit")
                    }
                    license {
                        name.set("Apache-2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0")
                    }
                }
                developers {
                    developer {
                        name.set("Tyson Lupul")
                        email.set("tyson@arboresce.ai")
                    }
                }
                scm {
                    connection.set("scm:git:https://github.com/arboresce/arboresce-ffi.git")
                    developerConnection.set(
                        "scm:git:ssh://git@github.com/arboresce/arboresce-ffi.git"
                    )
                    url.set("https://github.com/arboresce/arboresce-ffi")
                    tag.set("${project.version}")
                }
            }
        }
    }
    repositories {
        maven {
            name = "local"
            url = rootProject.layout.projectDirectory.dir("../../build/dist/maven").asFile.toURI()
        }
    }
}

tasks.register<Copy>("copyRuntimeDependencies") {
    from(configurations.runtimeClasspath)
    into(layout.buildDirectory.dir("runtime"))
}

dependencies {
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.10.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.1")
}

tasks.test {
    useJUnitPlatform()
    systemProperty("arboresce.consumer.classpath", sourceSets.test.get().runtimeClasspath.asPath)
    testLogging { events("passed", "skipped", "failed") }
}
