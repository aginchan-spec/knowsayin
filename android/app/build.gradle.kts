plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val knowsayinRimeRoot = providers.gradleProperty("knowsayinRimeRoot")
    .orElse(providers.environmentVariable("KNOWSAYIN_RIME_ROOT"))
    .orElse("/home/dnachan/build/knowsayin-rime/install")
    .get()

android {
    namespace = "com.knowsayin.android"
    compileSdk = 36
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "com.knowsayin.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        externalNativeBuild {
            cmake {
                cppFlags("-std=c++17")
                arguments(
                    "-DANDROID_STL=c++_static",
                    "-DKNOWSAYIN_RIME_ROOT=$knowsayinRimeRoot",
                )
            }
        }

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    buildTypes {
        debug {
            isDebuggable = true
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = false
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
}

dependencies {
    // Unit test
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")

    // AndroidX core for IME service support
    implementation("androidx.core:core-ktx:1.15.0")
}
