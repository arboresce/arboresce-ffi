plugins {
    id("com.android.library") version "8.13.0"
    `maven-publish`
}

group = "ai.arboresce"

version = "0.0.0"

description = "Kotlin SDK for Arboresce."

android {
    namespace = "ai.arboresce.android"
    compileSdk = 36
    defaultConfig { minSdk = 28 }
    sourceSets["main"].jniLibs.srcDir("../../../build/android/jni")
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    publishing { singleVariant("release") }
}

dependencies {
    api("ai.arboresce:arboresce:0.0.0") { exclude(group = "net.java.dev.jna", module = "jna") }
    implementation("net.java.dev.jna:jna:5.17.0@aar")
}

val sourcesJar by
    tasks.registering(Jar::class) {
        archiveClassifier.set("sources")
        from("src/main") { exclude("jniLibs/**") }
        from(files("../LICENSE-MIT", "../LICENSE-APACHE")) { into("META-INF") }
    }
val apiDocsJar by
    tasks.registering(Jar::class) {
        dependsOn(gradle.includedBuild("arboresce").task(":lib:dokkaGeneratePublicationHtml"))
        archiveClassifier.set("javadoc")
        from("../lib/build/dokka/html")
        from(files("../LICENSE-MIT", "../LICENSE-APACHE")) { into("META-INF") }
    }

afterEvaluate {
    publishing {
        publications {
            create<MavenPublication>("android") {
                artifactId = "arboresce-android"
                from(components["release"])
                artifact(sourcesJar)
                artifact(apiDocsJar)
                pom {
                    name.set("Arboresce Android")
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
                        url.set("https://github.com/arboresce/arboresce-ffi")
                        tag.set("${project.version}")
                    }
                }
            }
        }
        repositories {
            maven {
                name = "local"
                url = layout.projectDirectory.dir("../../../build/dist/maven").asFile.toURI()
            }
        }
    }
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.withType<Zip>().configureEach {
    if (name == "bundleReleaseAar") {
        from(files("../LICENSE-MIT", "../LICENSE-APACHE")) { into("META-INF") }
    }
}
