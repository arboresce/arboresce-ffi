plugins { id("com.android.application") version "8.13.0" }

android {
    namespace = "ai.arboresce.consumer"
    compileSdk = 36
    buildToolsVersion = "36.0.0"
    defaultConfig {
        applicationId = "ai.arboresce.consumer"
        minSdk = 28
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
        targetSdk = 36
        versionCode = 1
        versionName = "1"
    }
}

dependencies { implementation("ai.arboresce:arboresce-android:0.0.0") }
