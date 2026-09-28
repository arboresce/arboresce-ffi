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
        if (file("repository").isDirectory) {
            exclusiveContent {
                forRepository { maven { url = uri("repository") } }
                filter { includeGroup("ai.arboresce") }
            }
        }
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
