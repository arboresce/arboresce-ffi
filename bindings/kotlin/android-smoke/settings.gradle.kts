pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven { url = uri("repository") }
    }
}

rootProject.name = "arboresce-consumer"

if (!file("repository").exists()) {
    val sdk = file(providers.gradleProperty("sdkSource").orNull ?: "..")
    includeBuild(sdk.resolve("android"))
    includeBuild(sdk) {
        dependencySubstitution {
            substitute(module("ai.arboresce:arboresce")).using(project(":lib"))
        }
    }
}
