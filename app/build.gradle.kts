plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "cl.ingenieria.freecadmacrostudio"
    compileSdk = 35

    defaultConfig {
        applicationId = "cl.ingenieria.freecadmacrostudio"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
}

kotlin { jvmToolchain(17) }
