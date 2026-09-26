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
    }
}

rootProject.name = "arboresce-android"

includeBuild("..") {
    name = "arboresce"
    dependencySubstitution { substitute(module("ai.arboresce:arboresce")).using(project(":lib")) }
}
