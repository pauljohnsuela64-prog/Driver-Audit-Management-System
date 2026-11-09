import java.io.File
import java.util.Base64

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Explicit custodian opt-in only. PR/debug/configuration checks never need keys.
val offlineProductionSigning = providers.environmentVariable("BHLI_ANDROID_ENABLE_PRODUCTION_SIGNING")
    .orNull == "1"
fun signingInput(name: String): String = providers.environmentVariable(name).orNull
    ?.takeIf { it.isNotBlank() } ?: throw GradleException("Required external signing input is unavailable.")
val offlineKeyFile = if (offlineProductionSigning) {
    val candidate = File(signingInput("BHLI_ANDROID_KEYSTORE"))
    val repository = rootProject.projectDir.parentFile.parentFile.canonicalFile.toPath()
    require(candidate.isAbsolute && candidate.isFile &&
        !candidate.canonicalFile.toPath().startsWith(repository)) {
        "Production keystore must be an existing absolute file outside the repository."
    }
    candidate
} else null

// Direct packaging requests fail before dependency resolution; the graph gate below
// also covers aggregate tasks and abbreviated task selection.
val directOfflinePackaging = setOf("assembleOfflineRelease", "bundleOfflineRelease",
    "packageOfflineRelease", "validateSigningOfflineRelease")
if (gradle.startParameter.taskNames.any { it.substringAfterLast(':') in directOfflinePackaging }) {
    check(offlineProductionSigning) { "Offline release packaging requires explicitly authorized external production signing." }
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
        layout.buildDirectory.dir("generated/application-notices").get().asFile
    )

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.bhli.audit.mobile"
        manifestPlaceholders["appLabel"] = "BHLI Audit"
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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (offlineProductionSigning) {
            create("offlineProduction") {
                storeType = "PKCS12"
                storeFile = offlineKeyFile
                storePassword = signingInput("BHLI_ANDROID_STORE_PASSWORD")
                keyAlias = signingInput("BHLI_ANDROID_KEY_ALIAS").also {
                    require(!it.equals("androiddebugkey", ignoreCase = true)) { "Development signing is not production signing." }
                }
                keyPassword = signingInput("BHLI_ANDROID_KEY_PASSWORD")
            }
        }
    }

    flavorDimensions += "edition"
    productFlavors {
        create("online") {
            dimension = "edition"
        }
        create("offline") {
            dimension = "edition"
            applicationId = "com.bhli.audit.offline"
            versionNameSuffix = "-offline-dev"
            if (offlineProductionSigning) {
                signingConfig = signingConfigs.getByName("offlineProduction")
            }
            manifestPlaceholders["appLabel"] = "BHLI Audit Offline"
        }
    }

    buildTypes {
        release {
            // No debug-signing fallback. Online release behavior is unchanged.
            isDebuggable = false
        }
    }
}

// Override ONLY offlineRelease; online and accepted offlineDebug remain 1.0.0+2/dev.
androidComponents {
    onVariants(selector().withFlavor("edition" to "offline").withBuildType("release")) { variant ->
        variant.outputs.forEach { output ->
            output.versionName.set("1.0.0")
            output.versionCode.set(3)
        }
        tasks.register("verifyOfflineReleaseConfiguration") {
            doLast {
                check(variant.applicationId.get() == "com.bhli.audit.offline")
                check(!android.buildTypes.getByName("release").isDebuggable)
                variant.outputs.forEach {
                    check(it.versionName.get() == "1.0.0" && it.versionCode.get() == 3)
                }
                println("Offline release metadata verified: com.bhli.audit.offline / 1.0.0 / 3 / non-debug")
            }
        }
    }
    onVariants(selector().withBuildType("debug")) { variant ->
        val offline = variant.productFlavors.any { it.first == "edition" && it.second == "offline" }
        tasks.register(if (offline) "verifyOfflineDebugConfiguration" else "verifyOnlineDebugConfiguration") {
            doLast {
                check(variant.applicationId.get() == if (offline) "com.bhli.audit.offline" else "com.bhli.audit.mobile")
                variant.outputs.forEach {
                    check(it.versionCode.get() == 2)
                    check(it.versionName.get() == if (offline) "1.0.0-offline-dev" else "1.0.0")
                }
                println("Existing debug metadata verified: " + variant.name)
            }
        }
    }
}

// Fail closed before executing a packaging task; manifest/configuration inspection is key-free.
gradle.taskGraph.whenReady {
    val packagesOfflineRelease = allTasks.any { task ->
        task.project == project && task.name.contains("OfflineRelease") &&
            listOf("package", "sign", "validateSigning", "assemble", "bundle").any { task.name.startsWith(it) }
    }
    if (packagesOfflineRelease) {
        check(offlineProductionSigning) { "Offline release packaging requires explicitly authorized external production signing." }
        val defines = providers.gradleProperty("dart-defines").orNull.orEmpty().split(",")
        val sourceVersion = Base64.getEncoder().encodeToString(
            "BHLI_OFFLINE_SOURCE_VERSION=1.0.0+3".toByteArray(Charsets.UTF_8))
        check(sourceVersion in defines) { "Offline release requires its reviewed backup source-version define." }
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

dependencies {
    // Match the existing locked integration_test runtime graph. AGP consistent
    // resolution rejects newer test-only versions against that reviewed graph.
    androidTestImplementation("androidx.test:runner:1.3.0")
    androidTestImplementation("androidx.test:rules:1.2.0")
}
