const { withAppBuildGradle } = require("expo/config-plugins");

/** Expo regenerates android/: release signing must survive every prebuild. */
module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (mod) => {
    if (mod.modResults.language !== "groovy") {
      throw new Error("Lonora release signing requires the Expo Groovy Android template");
    }
    if (mod.modResults.contents.includes("// Lonora private release signing")) return mod;
    const debugRelease = "signingConfig signingConfigs.debug";
    const releaseStart = mod.modResults.contents.indexOf("        release {");
    const replacementIndex = mod.modResults.contents.indexOf(debugRelease, releaseStart);
    if (releaseStart < 0 || replacementIndex < 0) {
      throw new Error("Android release signing template changed; refuse a debug-signed release");
    }
    mod.modResults.contents =
      mod.modResults.contents.slice(0, replacementIndex) +
      "// Signing configured below from the private build environment." +
      mod.modResults.contents.slice(replacementIndex + debugRelease.length);
    mod.modResults.contents += `
// Lonora private release signing. No keystore/password is committed or embedded.
def lonoraStorePath = System.getenv('LONORA_ANDROID_KEYSTORE')
def lonoraStorePassword = System.getenv('LONORA_ANDROID_STORE_PASSWORD')
def lonoraKeyAlias = System.getenv('LONORA_ANDROID_KEY_ALIAS')
def lonoraKeyPassword = System.getenv('LONORA_ANDROID_KEY_PASSWORD')
def lonoraSigningReady = lonoraStorePath && lonoraStorePassword && lonoraKeyAlias && lonoraKeyPassword
android.signingConfigs.create('lonoraRelease') {
    if (lonoraSigningReady) {
        storeFile file(lonoraStorePath)
        storePassword lonoraStorePassword
        keyAlias lonoraKeyAlias
        keyPassword lonoraKeyPassword
    }
}
android.buildTypes.release.signingConfig = android.signingConfigs.lonoraRelease
gradle.taskGraph.whenReady { graph ->
    if (graph.allTasks.any { it.path.startsWith(':app:') && it.name.toLowerCase().contains('release') }) {
        if (!lonoraSigningReady || !file(lonoraStorePath).isFile()) {
            throw new GradleException('Private Lonora release signing is missing. Run scripts/android-release.py; never use the debug certificate for a release.')
        }
    }
}
`;
    return mod;
  });
};
