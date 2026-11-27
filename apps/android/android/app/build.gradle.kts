import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

/*
 * Release signing.
 *
 * The signing identity never lives in this repository. It is read, in order, from:
 *   1. Environment variables (CI): LONORA_ANDROID_KEYSTORE (path), LONORA_ANDROID_KEYSTORE_PASSWORD,
 *      LONORA_ANDROID_KEY_ALIAS, LONORA_ANDROID_KEY_PASSWORD.
 *   2. A properties file named by LONORA_ANDROID_SIGNING_PROPERTIES, or by default
 *      $XDG_CONFIG_HOME/lonora/android-native/signing.properties (~/.config/... when unset), with
 *      keys storeFile, storePassword, keyAlias, keyPassword.
 * A release build without a complete identity fails instead of silently using the debug key.
 */
data class ReleaseSigning(val storeFile: File, val storePassword: String, val keyAlias: String, val keyPassword: String)

fun loadReleaseSigning(): ReleaseSigning? {
    val env = System.getenv()
    val envStore = env["LONORA_ANDROID_KEYSTORE"]
    if (!envStore.isNullOrBlank()) {
        val storePassword = env["LONORA_ANDROID_KEYSTORE_PASSWORD"]
        val alias = env["LONORA_ANDROID_KEY_ALIAS"]
        val keyPassword = env["LONORA_ANDROID_KEY_PASSWORD"] ?: storePassword
        require(!storePassword.isNullOrBlank() && !alias.isNullOrBlank() && !keyPassword.isNullOrBlank()) {
            "LONORA_ANDROID_KEYSTORE is set but the password or alias variables are missing."
        }
        return ReleaseSigning(File(envStore), storePassword, alias, keyPassword)
    }
    val configHome = env["XDG_CONFIG_HOME"]?.takeIf { it.isNotBlank() } ?: "${System.getProperty("user.home")}/.config"
    val propsFile = File(env["LONORA_ANDROID_SIGNING_PROPERTIES"] ?: "$configHome/lonora/android-native/signing.properties")
    if (!propsFile.isFile) return null
    val props = Properties().apply { propsFile.inputStream().use { load(it) } }
    val storePath = props.getProperty("storeFile") ?: return null
    val store = File(storePath).let { if (it.isAbsolute) it else File(propsFile.parentFile, storePath) }
    return ReleaseSigning(
        store,
        props.getProperty("storePassword") ?: return null,
        props.getProperty("keyAlias") ?: return null,
        props.getProperty("keyPassword") ?: props.getProperty("storePassword"),
    )
}

val releaseSigning = loadReleaseSigning()

android {
    namespace = "ai.lonora.android"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    buildFeatures {
        resValues = true
        buildConfig = false
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        applicationId = "ai.lonora.android"
        // Minimum: Android 8.0 (API 26).
        minSdk = 26
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        resValue("string", "app_name", "Lonora")
    }

    signingConfigs {
        if (releaseSigning != null) {
            create("release") {
                storeFile = releaseSigning.storeFile
                storePassword = releaseSigning.storePassword
                keyAlias = releaseSigning.keyAlias
                keyPassword = releaseSigning.keyPassword
                enableV1Signing = false
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            resValue("string", "app_name", "Lonora Debug")
        }
        release {
            signingConfig = signingConfigs.findByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = false
        }
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// Refuse to produce an unsigned or debug-signed release artifact.
gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { t ->
        t.project == project && (t.name.startsWith("assembleRelease") || t.name.startsWith("bundleRelease") || t.name.startsWith("packageRelease"))
    }
    if (wantsRelease && releaseSigning == null) {
        throw GradleException(
            "Release signing identity not found. Set LONORA_ANDROID_KEYSTORE* variables or create " +
                "~/.config/lonora/android-native/signing.properties (see apps/android/README.md).",
        )
    }
}
