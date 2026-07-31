#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_COMMIT="e790073e1c311feb1ff423ba910f398df01bb60e"
SOURCE_REPOSITORY="https://github.com/leejet/stable-diffusion.cpp"
PACKAGE_NAME="stable-diffusion.cpp-macos-15-arm64"
ARCHIVE_NAME="e790073.zip"
SOURCE="${YTS_SDC_SOURCE:-$ROOT/desktop/vendor/stable-diffusion.cpp}"
ARTIFACT_ROOT="${YTS_MODEL_ARTIFACT_ROOT:-$ROOT/artifacts/download}"
RELEASE_DIR="$ARTIFACT_ROOT/sd/mac15-arm64"
BUILD_DIR="$SOURCE/build"
SD_CLI="$BUILD_DIR/bin/sd-cli"

fail() {
  echo "package stable-diffusion.cpp: $*" >&2
  exit 1
}

[ -d "$SOURCE" ] || fail "source directory does not exist: $SOURCE"
[ -f "$SOURCE/LICENSE" ] || fail "missing source license: $SOURCE/LICENSE"
[ -f "$SOURCE/ggml/LICENSE" ] || fail "missing ggml license: $SOURCE/ggml/LICENSE"

actual_commit="$(git -C "$SOURCE" rev-parse HEAD)"
[ "$actual_commit" = "$SOURCE_COMMIT" ] || \
  fail "expected source commit $SOURCE_COMMIT, got $actual_commit"

export YTS_SDC_SOURCE="$SOURCE"
cmake -S "$SOURCE" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DSD_METAL=ON \
  -DSD_BUILD_SHARED_LIBS=OFF \
  -DSD_BUILD_SHARED_GGML_LIB=OFF \
  -DSD_BUILD_EXAMPLES=ON
cmake --build "$BUILD_DIR" --config Release --target sd-cli -j

[ -x "$SD_CLI" ] || fail "build did not produce executable: $SD_CLI"
file "$SD_CLI" | grep -Eq 'Mach-O 64-bit executable arm64$' || \
  fail "sd-cli is not an arm64-only Mach-O executable"

build_info="$(vtool -show-build "$SD_CLI")"
printf '%s\n' "$build_info" | grep -Eq '^[[:space:]]*platform MACOS$' || \
  fail "sd-cli does not target macOS"
printf '%s\n' "$build_info" | grep -Eq '^[[:space:]]*minos 15\.0$' || \
  fail "sd-cli deployment target is not macOS 15.0"

while IFS= read -r dependency; do
  case "$dependency" in
    /System/Library/*|/usr/lib/*) ;;
    *) fail "sd-cli has non-system dynamic dependency: $dependency" ;;
  esac
done < <(otool -L "$SD_CLI" | tail -n +2 | awk '{print $1}')

"$SD_CLI" --help >/dev/null || fail "sd-cli --help smoke test failed"

staging_root="$(mktemp -d "${TMPDIR:-/tmp}/yts-sdcpp-package.XXXXXX")"
trap 'rm -rf "$staging_root"' EXIT
package_dir="$staging_root/$PACKAGE_NAME"
mkdir -p "$package_dir" "$RELEASE_DIR"
cp "$SD_CLI" "$package_dir/sd"
cp "$SOURCE/LICENSE" "$package_dir/LICENSE"
cp "$SOURCE/ggml/LICENSE" "$package_dir/ggml-LICENSE"
chmod 755 "$package_dir/sd"

executable_sha256="$(shasum -a 256 "$package_dir/sd" | awk '{print $1}')"
cat > "$package_dir/manifest.json" <<EOF
{
  "architecture": "arm64",
  "executable": "sd",
  "executable_sha256": "$executable_sha256",
  "licenses": ["LICENSE", "ggml-LICENSE"],
  "minimum_macos": "15.0",
  "platform": "macos",
  "source_commit": "$SOURCE_COMMIT",
  "source_repository": "$SOURCE_REPOSITORY"
}
EOF

touch -t 202001010000 \
  "$package_dir/sd" \
  "$package_dir/LICENSE" \
  "$package_dir/ggml-LICENSE" \
  "$package_dir/manifest.json"

archive="$RELEASE_DIR/$ARCHIVE_NAME"
rm -f "$archive" "$archive.sha256"
(
  cd "$staging_root"
  COPYFILE_DISABLE=1 zip -X -q "$archive" \
    "$PACKAGE_NAME/sd" \
    "$PACKAGE_NAME/LICENSE" \
    "$PACKAGE_NAME/ggml-LICENSE" \
    "$PACKAGE_NAME/manifest.json"
)
archive_sha256="$(shasum -a 256 "$archive" | awk '{print $1}')"
printf '%s\n' "$archive_sha256" > "$archive.sha256"

echo "artifact: $archive"
echo "sha256:  $archive_sha256"
