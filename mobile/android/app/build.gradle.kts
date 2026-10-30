plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Copy only the approved project license/scope documents, never the repository.
val prepareApplicationNotices = tasks.register<Sync>("prepareApplicationNotices") {
    from(rootProject.file("../..")) {
        include("LICENSE", "NOTICE", "ASSET_RIGHTS.md", "THIRD_PARTY_NOTICES.md",
            "docs/THIRD_PARTY_COMPLIANCE.md")
    }
    into(layout.buildDirectory.dir("generated/application-notices/application-license"))
}

android {
    namespace = "com.bhli.audit.mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    // Reviewed upstream notices/source material only; no application license grant.
    sourceSets.getByName("main").assets.srcDir(
        rootProject.file("../../packaging/notices/android/assets")
    )
    sourceSets.getByName("main").assets.srcDir(
        layout.buildDirectory.dir("generated/application-notices")
    )

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.bhli.audit.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // Phase 4A has no production signing or release distribution.
        }
    }
}

tasks.named("preBuild") { dependsOn(prepareApplicationNotices) }

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
