# Native librime Integration

Current app state: **JNI stub only**. The `StubRimeEngine` echoes typed pinyin and
returns simple hardcoded candidates for demo/development. The Android app does
not yet link native librime or replace the Kotlin stub engine.

Current dependency state: `android/scripts/build-librime-deps.sh` prepares
static Android librime dependency prefixes outside the repo. Verified on vm101
with Android NDK `27.2.12479018` for:

- `arm64-v8a`
- `armeabi-v7a`
- `x86_64`

Default external cache/build path:

```bash
~/build/knowsayin-rime
```

## Dependency build script

From the repo root:

```bash
android/scripts/build-librime-deps.sh --abi arm64-v8a --fetch-only
android/scripts/build-librime-deps.sh --abi arm64-v8a --dry-run
android/scripts/build-librime-deps.sh --all
```

Useful flags:

- `--abi <abi>` builds one ABI; may be repeated.
- `--all` builds `arm64-v8a`, `armeabi-v7a`, and `x86_64`.
- `--clean` removes selected ABI build/install outputs before rebuilding.
- `--fetch-only` clones/downloads external sources only.
- `--dry-run` prints the planned commands without writing build products.
- `--root <dir>` overrides the external build/cache root.

The script pins and stages:

- librime `1.16.1`
- Boost `1.84.0` headers
- Snappy `1.2.2`
- librime submodule deps: yaml-cpp, LevelDB, marisa-trie, OpenCC

Per-ABI output lands at:

```text
~/build/knowsayin-rime/install/<abi>/
  include/
  lib/
    librime.a
    libleveldb.a
    libmarisa.a
    libopencc.a
    libsnappy.a
    libyaml-cpp.a
```

Notes:

- OpenCC's full install/data target tries to run a target-built `opencc_dict`
  binary during cross-compilation. The script builds the Android `libopencc.a`
  target and manually stages headers/library instead.
- LevelDB is currently built without linking Snappy, while standalone
  `libsnappy.a` is staged for future use.
- OpenCC runtime config/dictionary data is not bundled by this script. A future
  asset task should prepare permitted OpenCC data and app extraction paths.

## Integration plan

When ready to integrate the real librime engine:

1. Use `android/scripts/build-librime-deps.sh --all` to refresh static
   dependency prefixes.
2. Update app CMake to link the per-ABI static libraries into
   `libknowsayin-rime.so`.
3. Replace the JNI stubs in `rime_jni.cpp` with librime C API calls.
4. Add a `JNIRimeEngine` implementation that calls `RimeJniBridge`.
5. Add only license-safe, KnowSayin-owned or permissively licensed Rime schemas
   and dictionaries.

## License safety

- librime core: BSD 3-Clause - safe for proprietary/commercial use.
- Boost: BSL-1.0.
- Snappy, LevelDB, glog/googletest submodules: BSD-style licenses.
- yaml-cpp: MIT.
- OpenCC: Apache-2.0.
- marisa-trie is dual-licensed; KnowSayin elects the BSD-2-Clause option.
- rime-pinyin-simp dictionary: Apache-2.0 - safe to bundle.
  (Derived from AOSP PinyinIME; see rime report for details.)
- All schemas must be written from scratch (KnowSayin-owned).
- Do NOT bundle: GPL schemas (brise, rime-ice, oh-my-rime),
  librime-octagram (GPL-3.0-only), or Trime source code (GPL-3.0).
- Build librime with:
  - `BUILD_MERGED_PLUGINS=OFF`
  - `ENABLE_EXTERNAL_PLUGINS=OFF`
  - `BUILD_TEST=OFF`
  - `BUILD_SAMPLE=OFF`
- Do not fetch or bundle Trime, plum, brise, rime-ice, or oh-my-rime assets.

## Reference (architecture only — do not copy code)

- fcitx5-android: clean Kotlin/CMake JNI bridge pattern.
- AOSP LatinIME: InputMethodService lifecycle reference.
- librime API: https://github.com/rime/librime

Full integration report: MemoryBank/reports/active/knowsayin/rime.md
