#!/usr/bin/env bash
# Builds the signed release APK of Lonora for Android on a plain Linux build server (Flutter
# 3.47.9 and the Android SDK) and writes, into OUTPUT_DIR:
#
#   lonora-android-<version>.apk   the release APK
#   lonora-android.json            its in-app update manifest, pointing at
#                                  https://lonora.io/download/lonora-android-<version>.apk
#
# The build looks for updates at https://lonora.io/download/lonora-android.json.
#
# The signing identity lives on the build server only, never in the repository. It comes from
# LONORA_ANDROID_KEYSTORE (path), LONORA_ANDROID_KEYSTORE_PASSWORD, LONORA_ANDROID_KEY_ALIAS and
# LONORA_ANDROID_KEY_PASSWORD (defaults to the keystore password), or else from the properties
# file android/app/build.gradle.kts reads (LONORA_ANDROID_SIGNING_PROPERTIES, by default
# ~/.config/lonora/android-native/signing.properties). Nothing secret is ever printed.
#
# Usage: tool/build_release.sh [--build-number N] OUTPUT_DIR
set -euo pipefail

readonly FLUTTER_VERSION=3.47.9
readonly UPDATE_MANIFEST=https://lonora.io/download/lonora-android.json
readonly DOWNLOAD_BASE=https://lonora.io/download

usage() {
  echo "Usage: tool/build_release.sh [--build-number N] OUTPUT_DIR"
}

fail() {
  echo "build_release: $*" >&2
  exit 1
}

build_number=""
build_number_given=false
out=""
while (($# > 0)); do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --build-number)
      (($# >= 2)) || fail "--build-number needs a value"
      build_number="$2"
      build_number_given=true
      shift 2
      ;;
    --build-number=*)
      build_number="${1#--build-number=}"
      build_number_given=true
      shift
      ;;
    -*)
      usage >&2
      fail "unknown option: $1"
      ;;
    *)
      [[ -z "$out" ]] || fail "one output folder only (got '$out' and '$1')"
      out="$1"
      shift
      ;;
  esac
done

[[ -n "$out" ]] || {
  usage >&2
  fail "missing the output folder"
}
# Android's versionCode: a positive integer up to 2100000000.
if [[ "$build_number_given" == true ]] &&
  { [[ ! "$build_number" =~ ^[1-9][0-9]{0,9}$ ]] || ((build_number > 2100000000)); }; then
  fail "--build-number must be a whole number from 1 to 2100000000 (got '$build_number')"
fi

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
repo_dir="$(cd "$app_dir/../.." && pwd -P)"

# A file of the signing identity, by its real path (no "..", no symlink), which must lie outside
# the repository: nothing there ignores keystores, so one could be committed.
outside_repo() {
  local real
  real="$(realpath -e -- "$1")" || fail "cannot resolve $1"
  case "$real" in
    "$repo_dir"/*) fail "the signing identity must stay outside the repository: $1 is $real" ;;
  esac
  printf '%s\n' "$real"
}

# The signing identity: checked here so a missing piece fails before a long build. Only names
# and paths are ever printed, never a password.
if [[ -n "${LONORA_ANDROID_KEYSTORE:-}" ]]; then
  keystore="$LONORA_ANDROID_KEYSTORE"
  [[ "$keystore" = /* ]] || keystore="$PWD/$keystore"
  [[ -f "$keystore" && -r "$keystore" ]] ||
    fail "LONORA_ANDROID_KEYSTORE does not name a readable file: $keystore"
  [[ -n "${LONORA_ANDROID_KEYSTORE_PASSWORD:-}" ]] ||
    fail "LONORA_ANDROID_KEYSTORE_PASSWORD is not set"
  [[ -n "${LONORA_ANDROID_KEY_ALIAS:-}" ]] || fail "LONORA_ANDROID_KEY_ALIAS is not set"
  keystore="$(outside_repo "$keystore")"
  # Gradle resolves a relative path from its own folder: hand it the absolute one.
  export LONORA_ANDROID_KEYSTORE="$keystore"
  signing="$keystore"
else
  props="${LONORA_ANDROID_SIGNING_PROPERTIES:-${XDG_CONFIG_HOME:-$HOME/.config}/lonora/android-native/signing.properties}"
  [[ "$props" = /* ]] || props="$PWD/$props"
  [[ -f "$props" && -r "$props" ]] ||
    fail "no signing identity: set LONORA_ANDROID_KEYSTORE, LONORA_ANDROID_KEYSTORE_PASSWORD, LONORA_ANDROID_KEY_ALIAS and LONORA_ANDROID_KEY_PASSWORD, or create $props (see apps/android/README.md)"
  for key in storeFile storePassword keyAlias; do
    grep -Eq "^[[:space:]]*$key[[:space:]]*[=:]" "$props" || fail "$props has no $key"
  done
  outside_repo "$props" >/dev/null
  # Its keystore, a relative path read from the properties file's folder (as build.gradle.kts).
  keystore="$(sed -nE 's/^[[:space:]]*storeFile[[:space:]]*[=:][[:space:]]*//p' "$props" |
    tail -n 1 | sed -E 's/[[:space:]]+$//')"
  [[ -n "$keystore" ]] || fail "$props has an empty storeFile"
  [[ "$keystore" = /* ]] || keystore="$(dirname -- "$props")/$keystore"
  [[ -f "$keystore" && -r "$keystore" ]] ||
    fail "the storeFile of $props does not name a readable file: $keystore"
  outside_repo "$keystore" >/dev/null
  export LONORA_ANDROID_SIGNING_PROPERTIES="$props"
  signing="$props"
fi

command -v flutter >/dev/null || fail "flutter is not on PATH (Flutter $FLUTTER_VERSION is needed)"
command -v python3 >/dev/null || fail "python3 is not on PATH"
[[ -n "${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}" ]] ||
  fail "set ANDROID_HOME to the Android SDK (its build-tools sign-check the APK)"
flutter_version="$(flutter --version --machine 2>/dev/null |
  sed -nE 's/.*"frameworkVersion": *"([^"]+)".*/\1/p')" ||
  fail "could not run flutter --version"
[[ "$flutter_version" == "$FLUTTER_VERSION" ]] ||
  fail "Flutter $FLUTTER_VERSION is needed, found '${flutter_version:-unknown}'"

# Relative to where the script was started from.
mkdir -p -- "$out" || fail "cannot create the output folder '$out'"
out="$(cd -- "$out" && pwd)"

cd "$app_dir"
version="$(sed -nE 's/^version:[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+)(\+[0-9]+)?[[:space:]]*$/\1/p' pubspec.yaml)"
[[ -n "$version" ]] || fail "could not read the version (x.y.z) from pubspec.yaml"

echo "Building Lonora for Android $version${build_number:+ (build $build_number)}, signed with $signing"
flutter pub get --enforce-lockfile
flutter build apk --release \
  --dart-define="LONORA_UPDATE_MANIFEST=$UPDATE_MANIFEST" \
  ${build_number:+"--build-number=$build_number"}

built="build/app/outputs/flutter-apk/app-release.apk"
[[ -f "$built" ]] || fail "the build did not produce $built"

apk_name="lonora-android-$version.apk"
apk="$out/$apk_name"
manifest="$out/lonora-android.json"
# Both are written next to their final names and checked before either moves into place, the
# manifest last: a download folder never offers a manifest whose APK is missing or half-written,
# and an APK of another version never replaces the published one. Leftovers go on any exit.
trap 'rm -f -- "$apk.partial" "$manifest.partial"' EXIT
cp -- "$built" "$apk.partial"
python3 tool/release_manifest.py "$apk.partial" --update-manifest "$DOWNLOAD_BASE/$apk_name" >"$manifest.partial" ||
  fail "could not write the update manifest"
manifest_version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version_name"])' "$manifest.partial")"
[[ "$manifest_version" == "$version" ]] ||
  fail "the APK says version '$manifest_version', pubspec.yaml says '$version'"
mv -f -- "$apk.partial" "$apk"
mv -f -- "$manifest.partial" "$manifest"

echo "Wrote $apk"
echo "Wrote $manifest"
# Public verification metadata (file and signer SHA-256, versions); nothing secret.
python3 tool/release_manifest.py "$apk"
