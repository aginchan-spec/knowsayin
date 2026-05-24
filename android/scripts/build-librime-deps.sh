#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ROOT="${HOME}/build/knowsayin-rime"
DEFAULT_ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-${HOME}/android-sdk}}"
DEFAULT_NDK_VERSION="27.2.12479018"
DEFAULT_API="26"
DEFAULT_LIBRIME_REF="1.16.1"
DEFAULT_BOOST_VERSION="1.84.0"
DEFAULT_SNAPPY_REF="1.2.2"

ALL_ABIS=("arm64-v8a" "armeabi-v7a" "x86_64")

ROOT_DIR="${KNOWSAYIN_RIME_BUILD_ROOT:-${DEFAULT_ROOT}}"
ANDROID_HOME_DIR="${DEFAULT_ANDROID_HOME}"
NDK_VERSION="${DEFAULT_NDK_VERSION}"
ANDROID_API="${DEFAULT_API}"
LIBRIME_REF="${LIBRIME_REF:-${DEFAULT_LIBRIME_REF}}"
BOOST_VERSION="${BOOST_VERSION:-${DEFAULT_BOOST_VERSION}}"
SNAPPY_REF="${SNAPPY_REF:-${DEFAULT_SNAPPY_REF}}"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '4')"

declare -a SELECTED_ABIS=()
DRY_RUN=0
FETCH_ONLY=0
CLEAN=0

usage() {
  cat <<'USAGE'
Build or prepare Android static librime dependencies outside the repo.

Usage:
  android/scripts/build-librime-deps.sh --abi arm64-v8a
  android/scripts/build-librime-deps.sh --all

Options:
  --abi ABI             Build one ABI. May be repeated. Supported: arm64-v8a, armeabi-v7a, x86_64.
  --all                 Build all supported ABIs.
  --clean               Remove selected ABI build/install dirs before building.
  --fetch-only          Fetch/update external sources and prepare Boost headers only.
  --dry-run             Print commands without executing them.
  --root DIR            External source/build/install root. Default: ~/build/knowsayin-rime.
  --android-home DIR    Android SDK root. Default: $ANDROID_HOME, $ANDROID_SDK_ROOT, or ~/android-sdk.
  --ndk-version VER     Android NDK version under android-home/ndk. Default: 27.2.12479018.
  --api API             Android API level. Default: 26.
  --jobs N              Parallel build jobs. Default: CPU count.
  --librime-ref REF     librime git tag/branch/commit. Default: 1.16.1.
  --boost-version VER   Boost source release used for headers. Default: 1.84.0.
  --snappy-ref REF      Snappy git tag/branch/commit. Default: 1.2.2.
  --help                Show this help.

Outputs:
  <root>/src/           External source checkouts/downloads.
  <root>/build/<abi>/   Per-ABI CMake build trees.
  <root>/install/<abi>/ Static libs and headers for later JNI linking.

GPL-safety defaults:
  librime is configured with BUILD_MERGED_PLUGINS=OFF, ENABLE_EXTERNAL_PLUGINS=OFF,
  BUILD_TEST=OFF, and BUILD_SAMPLE=OFF. This script does not fetch Trime, plum,
  brise, rime-ice, oh-my-rime, or other schema/dictionary assets.
  marisa-trie is dual-licensed; KnowSayin elects the BSD-2-Clause option.
USAGE
}

log() {
  printf '[build-librime-deps] %s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [[ "${DRY_RUN}" == "0" ]]; then
    "$@"
  fi
}

run_env() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [[ "${DRY_RUN}" == "0" ]]; then
    env "$@"
  fi
}

contains_abi() {
  local candidate="$1"
  local abi
  for abi in "${ALL_ABIS[@]}"; do
    [[ "${abi}" == "${candidate}" ]] && return 0
  done
  return 1
}

add_abi() {
  local abi="$1"
  contains_abi "${abi}" || die "unsupported ABI: ${abi}"
  local existing
  for existing in "${SELECTED_ABIS[@]}"; do
    [[ "${existing}" == "${abi}" ]] && return 0
  done
  SELECTED_ABIS+=("${abi}")
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --abi)
        [[ $# -ge 2 ]] || die "--abi requires a value"
        add_abi "$2"
        shift 2
        ;;
      --all)
        SELECTED_ABIS=("${ALL_ABIS[@]}")
        shift
        ;;
      --clean)
        CLEAN=1
        shift
        ;;
      --fetch-only)
        FETCH_ONLY=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --root)
        [[ $# -ge 2 ]] || die "--root requires a value"
        ROOT_DIR="$2"
        shift 2
        ;;
      --android-home)
        [[ $# -ge 2 ]] || die "--android-home requires a value"
        ANDROID_HOME_DIR="$2"
        shift 2
        ;;
      --ndk-version)
        [[ $# -ge 2 ]] || die "--ndk-version requires a value"
        NDK_VERSION="$2"
        shift 2
        ;;
      --api)
        [[ $# -ge 2 ]] || die "--api requires a value"
        ANDROID_API="$2"
        shift 2
        ;;
      --jobs)
        [[ $# -ge 2 ]] || die "--jobs requires a value"
        JOBS="$2"
        shift 2
        ;;
      --librime-ref)
        [[ $# -ge 2 ]] || die "--librime-ref requires a value"
        LIBRIME_REF="$2"
        shift 2
        ;;
      --boost-version)
        [[ $# -ge 2 ]] || die "--boost-version requires a value"
        BOOST_VERSION="$2"
        shift 2
        ;;
      --snappy-ref)
        [[ $# -ge 2 ]] || die "--snappy-ref requires a value"
        SNAPPY_REF="$2"
        shift 2
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "unknown option: $1"
        ;;
    esac
  done

  if [[ ${#SELECTED_ABIS[@]} -eq 0 ]]; then
    add_abi "arm64-v8a"
  fi
}

abs_path() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s/%s\n' "$(pwd)" "${path}"
  fi
}

find_tool() {
  local explicit="$1"
  local fallback="$2"
  local name="$3"
  if [[ -x "${explicit}" ]]; then
    printf '%s\n' "${explicit}"
  elif command -v "${fallback}" >/dev/null 2>&1; then
    command -v "${fallback}"
  else
    die "missing ${name}; expected ${explicit} or ${fallback} on PATH"
  fi
}

configure_paths() {
  ROOT_DIR="$(abs_path "${ROOT_DIR}")"
  SRC_DIR="${ROOT_DIR}/src"
  DOWNLOAD_DIR="${ROOT_DIR}/downloads"
  BUILD_DIR="${ROOT_DIR}/build"
  INSTALL_DIR="${ROOT_DIR}/install"
  STATUS_DIR="${ROOT_DIR}/status"

  NDK_DIR="${ANDROID_HOME_DIR}/ndk/${NDK_VERSION}"
  TOOLCHAIN_FILE="${NDK_DIR}/build/cmake/android.toolchain.cmake"
  CMAKE_BIN="$(find_tool "${ANDROID_HOME_DIR}/cmake/3.22.1/bin/cmake" "cmake" "CMake")"
  NINJA_BIN="$(find_tool "${ANDROID_HOME_DIR}/cmake/3.22.1/bin/ninja" "ninja" "Ninja")"
  LLVM_AR="${NDK_DIR}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-ar"

  [[ -d "${NDK_DIR}" ]] || die "Android NDK not found: ${NDK_DIR}"
  [[ -f "${TOOLCHAIN_FILE}" ]] || die "Android NDK toolchain file not found: ${TOOLCHAIN_FILE}"
  [[ -x "${LLVM_AR}" ]] || die "llvm-ar not found: ${LLVM_AR}"
  command -v git >/dev/null 2>&1 || die "git is required"
  command -v curl >/dev/null 2>&1 || die "curl is required"
  PYTHON_BIN="$(command -v python3 || true)"
  [[ -n "${PYTHON_BIN}" ]] || die "python3 is required"
}

prepare_dirs() {
  run mkdir -p "${SRC_DIR}" "${DOWNLOAD_DIR}" "${BUILD_DIR}" "${INSTALL_DIR}" "${STATUS_DIR}"
}

clean_abi() {
  local abi="$1"
  run rm -rf "${BUILD_DIR}/${abi}" "${INSTALL_DIR}/${abi}" "${STATUS_DIR}/${abi}.status"
}

git_checkout() {
  local repo_url="$1"
  local ref="$2"
  local dest="$3"
  if [[ ! -d "${dest}/.git" ]]; then
    run git clone "${repo_url}" "${dest}"
  fi
  run git -C "${dest}" fetch --tags --prune
  run git -C "${dest}" checkout "${ref}"
}

fetch_librime() {
  local dest="${SRC_DIR}/librime"
  git_checkout "https://github.com/rime/librime.git" "${LIBRIME_REF}" "${dest}"
  run git -C "${dest}" submodule update --init --recursive
}

fetch_snappy() {
  local dest="${SRC_DIR}/snappy"
  git_checkout "https://github.com/google/snappy.git" "${SNAPPY_REF}" "${dest}"
}

boost_archive_name() {
  local version_underscores="${BOOST_VERSION//./_}"
  printf 'boost_%s.tar.bz2\n' "${version_underscores}"
}

boost_src_dir() {
  local version_underscores="${BOOST_VERSION//./_}"
  printf '%s/boost_%s\n' "${SRC_DIR}" "${version_underscores}"
}

fetch_boost() {
  local archive
  local archive_path
  local url
  local dest
  archive="$(boost_archive_name)"
  archive_path="${DOWNLOAD_DIR}/${archive}"
  url="https://archives.boost.io/release/${BOOST_VERSION}/source/${archive}"
  dest="$(boost_src_dir)"

  if [[ ! -d "${dest}/boost" ]]; then
    if [[ ! -f "${archive_path}" ]]; then
      run curl -L --fail --output "${archive_path}" "${url}"
    fi
    run tar -xjf "${archive_path}" -C "${SRC_DIR}"
  fi
}

fetch_sources() {
  log "fetching sources under ${SRC_DIR}"
  fetch_librime
  fetch_snappy
  fetch_boost
}

common_cmake_args() {
  local abi="$1"
  local prefix="$2"
  printf '%s\0' \
    -G "Ninja" \
    "-DCMAKE_MAKE_PROGRAM=${NINJA_BIN}" \
    "-DCMAKE_TOOLCHAIN_FILE=${TOOLCHAIN_FILE}" \
    "-DANDROID_ABI=${abi}" \
    "-DANDROID_PLATFORM=android-${ANDROID_API}" \
    "-DANDROID_STL=c++_static" \
    "-DCMAKE_BUILD_TYPE=Release" \
    "-DCMAKE_INSTALL_PREFIX=${prefix}" \
    "-DCMAKE_POSITION_INDEPENDENT_CODE=ON" \
    "-DBUILD_SHARED_LIBS=OFF"
}

cmake_configure() {
  local abi="$1"
  local source="$2"
  local build="$3"
  local prefix="$4"
  shift 4
  local args=()
  while IFS= read -r -d '' arg; do
    args+=("${arg}")
  done < <(common_cmake_args "${abi}" "${prefix}")
  run "${CMAKE_BIN}" -S "${source}" -B "${build}" "${args[@]}" "$@"
}

cmake_build() {
  local build="$1"
  shift
  run "${CMAKE_BIN}" --build "${build}" --parallel "${JOBS}" "$@"
}

cmake_install() {
  local build="$1"
  run "${CMAKE_BIN}" --install "${build}"
}

stage_boost_headers() {
  local prefix="$1"
  local boost_src
  boost_src="$(boost_src_dir)"
  if [[ "${DRY_RUN}" == "0" ]]; then
    [[ -d "${boost_src}/boost" ]] || die "Boost headers missing: ${boost_src}/boost"
  fi
  run mkdir -p "${prefix}/include"
  run rm -rf "${prefix}/include/boost"
  run cp -R "${boost_src}/boost" "${prefix}/include/"
}

build_snappy() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/snappy"
  local build="${BUILD_DIR}/${abi}/snappy"
  log "${abi}: building snappy"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DSNAPPY_BUILD_TESTS=OFF \
    -DSNAPPY_BUILD_BENCHMARKS=OFF \
    -DSNAPPY_INSTALL=ON
  cmake_build "${build}"
  cmake_install "${build}"
}

build_yaml_cpp() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/librime/deps/yaml-cpp"
  local build="${BUILD_DIR}/${abi}/yaml-cpp"
  log "${abi}: building yaml-cpp"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DYAML_CPP_BUILD_TESTS=OFF \
    -DYAML_CPP_BUILD_TOOLS=OFF \
    -DYAML_CPP_INSTALL=ON \
    -DYAML_BUILD_SHARED_LIBS=OFF
  cmake_build "${build}"
  cmake_install "${build}"
}

build_leveldb() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/librime/deps/leveldb"
  local build="${BUILD_DIR}/${abi}/leveldb"
  log "${abi}: building leveldb"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DLEVELDB_BUILD_TESTS=OFF \
    -DLEVELDB_BUILD_BENCHMARKS=OFF \
    -DLEVELDB_INSTALL=ON \
    "-DCMAKE_IGNORE_PATH=${prefix}/lib/libsnappy.a"
  cmake_build "${build}" --target leveldb
  cmake_install "${build}"
}

build_marisa() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/librime/deps/marisa-trie"
  local build="${BUILD_DIR}/${abi}/marisa-trie"
  log "${abi}: building marisa-trie"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DENABLE_TOOLS=OFF \
    -DBUILD_TESTING=OFF \
    -DENABLE_NATIVE_CODE=OFF
  cmake_build "${build}" --target marisa
  cmake_install "${build}"
}

stage_opencc_headers() {
  local source="$1"
  local build="$2"
  local prefix="$3"
  local include_dir="${prefix}/include/opencc"
  run mkdir -p "${include_dir}"
  run cp "${source}"/src/*.hpp "${include_dir}/"
  run cp "${source}/src/opencc.h" "${include_dir}/"
  run cp "${build}/src/opencc_config.h" "${include_dir}/"
  if [[ -f "${build}/src/Opencc_Export.h" ]]; then
    run cp "${build}/src/Opencc_Export.h" "${include_dir}/"
  fi
}

build_opencc() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/librime/deps/opencc"
  local build="${BUILD_DIR}/${abi}/opencc"
  log "${abi}: building opencc static library"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DBUILD_DOCUMENTATION=OFF \
    -DENABLE_GTEST=OFF \
    -DENABLE_BENCHMARK=OFF \
    -DBUILD_PYTHON=OFF \
    -DUSE_SYSTEM_MARISA=ON \
    "-DLIBMARISA:FILEPATH=${prefix}/lib/libmarisa.a" \
    "-DPYTHON_EXECUTABLE=${PYTHON_BIN}" \
    "-DCMAKE_PREFIX_PATH=${prefix}" \
    "-DCMAKE_INCLUDE_PATH=${prefix}/include" \
    "-DCMAKE_LIBRARY_PATH=${prefix}/lib" \
    "-DCMAKE_CXX_FLAGS=-I${prefix}/include"
  cmake_build "${build}" --target libopencc
  run mkdir -p "${prefix}/lib"
  run cp "${build}/src/libopencc.a" "${prefix}/lib/libopencc.a"
  stage_opencc_headers "${source}" "${build}" "${prefix}"
}

build_librime() {
  local abi="$1"
  local prefix="$2"
  local source="${SRC_DIR}/librime"
  local build="${BUILD_DIR}/${abi}/librime"
  log "${abi}: building librime"
  cmake_configure "${abi}" "${source}" "${build}" "${prefix}" \
    -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_STATIC=ON \
    -DBUILD_MERGED_PLUGINS=OFF \
    -DENABLE_EXTERNAL_PLUGINS=OFF \
    -DENABLE_LOGGING=OFF \
    -DBUILD_TEST=OFF \
    -DBUILD_SAMPLE=OFF \
    -DBUILD_DATA=OFF \
    "-DCMAKE_PREFIX_PATH=${prefix}" \
    "-DCMAKE_INCLUDE_PATH=${prefix}/include" \
    "-DCMAKE_LIBRARY_PATH=${prefix}/lib" \
    "-DYamlCpp_INCLUDE_PATH=${prefix}/include" \
    "-DYamlCpp_NEW_API=${prefix}/include" \
    "-DYamlCpp_LIBRARY=${prefix}/lib/libyaml-cpp.a" \
    "-DLevelDb_INCLUDE_PATH=${prefix}/include" \
    "-DLevelDb_LIBRARY=${prefix}/lib/libleveldb.a" \
    "-DMarisa_INCLUDE_PATH=${prefix}/include" \
    "-DMarisa_LIBRARY=${prefix}/lib/libmarisa.a" \
    "-DOpencc_INCLUDE_PATH=${prefix}/include" \
    "-DOpencc_LIBRARY=${prefix}/lib/libopencc.a" \
    "-DBOOST_ROOT=${prefix}" \
    "-DBoost_INCLUDE_DIR=${prefix}/include" \
    -DBoost_NO_SYSTEM_PATHS=ON
  run_env RIME_PLUGINS= "${CMAKE_BIN}" --build "${build}" --parallel "${JOBS}" --target rime-static
  cmake_install "${build}"
}

write_status() {
  local abi="$1"
  local prefix="$2"
  local status_file="${STATUS_DIR}/${abi}.status"
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  {
    printf 'abi=%s\n' "${abi}"
    printf 'prefix=%s\n' "${prefix}"
    printf 'librime_ref=%s\n' "${LIBRIME_REF}"
    printf 'boost_version=%s\n' "${BOOST_VERSION}"
    printf 'snappy_ref=%s\n' "${SNAPPY_REF}"
    printf 'android_ndk=%s\n' "${NDK_DIR}"
    printf 'android_api=%s\n' "${ANDROID_API}"
    printf 'built_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    find "${prefix}/lib" -maxdepth 1 -type f -name '*.a' -printf 'lib=%p\n' | sort
  } > "${status_file}"
}

verify_artifacts() {
  local abi="$1"
  local prefix="$2"
  local lib
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  for lib in librime.a libleveldb.a libmarisa.a libopencc.a libsnappy.a libyaml-cpp.a; do
    [[ -f "${prefix}/lib/${lib}" ]] || die "${abi}: missing ${prefix}/lib/${lib}"
  done
  run "${LLVM_AR}" t "${prefix}/lib/librime.a"
}

build_abi() {
  local abi="$1"
  local prefix="${INSTALL_DIR}/${abi}"
  if [[ "${CLEAN}" == "1" ]]; then
    clean_abi "${abi}"
  fi
  run mkdir -p "${prefix}"
  stage_boost_headers "${prefix}"
  build_snappy "${abi}" "${prefix}"
  build_yaml_cpp "${abi}" "${prefix}"
  build_leveldb "${abi}" "${prefix}"
  build_marisa "${abi}" "${prefix}"
  build_opencc "${abi}" "${prefix}"
  build_librime "${abi}" "${prefix}"
  verify_artifacts "${abi}" "${prefix}"
  write_status "${abi}" "${prefix}"
  log "${abi}: complete; install prefix ${prefix}"
}

main() {
  parse_args "$@"
  configure_paths
  log "root: ${ROOT_DIR}"
  log "android ndk: ${NDK_DIR}"
  log "abis: ${SELECTED_ABIS[*]}"
  prepare_dirs
  fetch_sources

  if [[ "${FETCH_ONLY}" == "1" ]]; then
    log "fetch-only requested; sources prepared"
    exit 0
  fi

  local abi
  for abi in "${SELECTED_ABIS[@]}"; do
    build_abi "${abi}"
  done
}

main "$@"
