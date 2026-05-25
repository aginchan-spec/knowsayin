# Native librime Integration

Current app state: **real JNI librime session smoke + safe assets**. The JNI
shared library links real static librime dependencies for each Android ABI, and
`nativeGetVersion()` calls librime's C API through `rime_get_api()->get_version()`.
`JniRimeEngine` now extracts bundled assets, initializes librime with app-owned
user/shared data directories, selects `knowsayin_pinyin`, creates real sessions,
processes keys, reads context/candidates/commits, and destroys/finalizes
sessions through the C API.

The existing `StubRimeEngine` remains available as a fallback. `KnowSayinImeService`
tries `JniRimeEngine` first and falls back to the stub if native library load,
asset extraction, librime initialization, schema load, or session creation fails.
Native failure should degrade the IME rather than crash it.

Safe first pinyin assets are bundled in APK assets and extractable at runtime:
a KnowSayin-owned `knowsayin_pinyin` schema, minimal KnowSayin-owned
`default.yaml`/`symbols.yaml` Rime presets required by schema imports, the
permissively licensed `pinyin_simp.dict.yaml` dictionary (Apache-2.0, from
rime-pinyin-simp), and attribution/license files. `RimeAssetManager` handles
versioned extraction to app internal storage (`shared/` and `user/` directories).

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

The app CMake defaults to:

```text
/home/dnachan/build/knowsayin-rime/install
```

Override the root with Gradle property `knowsayinRimeRoot`, environment variable
`KNOWSAYIN_RIME_ROOT`, or CMake argument `-DKNOWSAYIN_RIME_ROOT=/path/to/install`.

Notes:

- OpenCC's full install/data target tries to run a target-built `opencc_dict`
  binary during cross-compilation. The script builds the Android `libopencc.a`
  target and manually stages headers/library instead.
- LevelDB is currently built without linking Snappy, while standalone
  `libsnappy.a` is staged for future use.
- OpenCC runtime config/dictionary data is not bundled by this script. A future
  asset task should prepare permitted OpenCC data and app extraction paths.

## Safe Rime assets

First-milestone simplified Chinese pinyin assets are bundled in
`app/src/main/assets/rime/` and extracted at runtime by `RimeAssetManager`:

| File | Source | License |
|---|---|---|
| `pinyin_simp.dict.yaml` | rime-pinyin-simp master | Apache-2.0 |
| `knowsayin_pinyin.schema.yaml` | KnowSayin-owned | KnowSayin copyright |
| `default.yaml` | KnowSayin-owned | KnowSayin copyright |
| `symbols.yaml` | KnowSayin-owned | KnowSayin copyright |
| `NOTICE` | KnowSayin-authored | N/A (attribution doc) |
| `LICENSE.apache-2.0` | rime-pinyin-simp master | Apache-2.0 |
| `ASSET_VERSION` | KnowSayin-managed | N/A |

The schema uses `script_translator` with dictionary `pinyin_simp` and imports
only the bundled minimal KnowSayin presets (`default`, `symbols`). No GPL/LGPL
assets, no OpenCC data, no rime-essay vocabulary, no stroke reverse-lookup.

Runtime extraction via `RimeAssetManager.extractIfNeeded(context)`:
- Shared assets → `context.filesDir/rime/shared/` (replaced on version bump).
- User data → `context.filesDir/rime/user/` (never deleted by extraction).
- Version tracking in `user/asset_version.txt`.
- Returns `Pair<File, File>` of (sharedDir, userDir) for native init.

## JNI session smoke

Implemented in `app/src/main/cpp/rime_jni.cpp`:

- `nativeInitialize(userDir, sharedDir)` sets `RimeTraits` with KnowSayin
  distribution/app metadata, calls librime setup/initialize, then runs
  maintenance/deploy work and joins the maintenance thread.
- Initialization is idempotent for the same dirs. Reinitializing with different
  dirs finalizes existing sessions first.
- `nativeCreateSession()` creates a real librime session and applies the stored
  default schema (`knowsayin_pinyin`).
- `nativeDestroySession()`, `nativeSessionExists()`, and `nativeFinalize()` call
  real session/finalize APIs.
- `nativeProcessKey()` maps ASCII and common Android key constants to Rime/X11
  keysyms, including Backspace, Enter, arrows, page/home/end, punctuation, and
  modifier masks.
- `nativeSimulateKeySequence()` uses librime's sequence helper when available,
  falling back to ASCII character processing.
- `nativeGetContext()` returns compact JSON:
  `composition`, `compositionCursor`, `candidates`, `highlightedIndex`,
  `isComposing`.
- `nativeGetCommit()` reads and frees `RimeCommit`.
- Candidate select/highlight use current-page APIs when available.

Narrow or partial API surfaces:

- `nativeLoadSchema(schemaId)` stores the default schema and validates it when
  librime is initialized. Because the JNI signature has no session id, the
  schema is applied to new sessions.
- `nativeSetOption()` is real for a provided session id.
- `nativeGetProperty()` exposes only safe global diagnostics such as version,
  default schema, initialized status, and data dirs. It does not read
  session-specific properties because the JNI signature has no session id.
- `nativeConfigure()` currently supports only changing the stored default schema.
  General config persistence is not implemented.
- `nativeStartMaintenance()` is real and joins the maintenance thread.

No raw user input, commit text, context JSON, or candidate text is logged by the
KnowSayin JNI layer.

## Integration plan

For the next native integration step:

1. Use `android/scripts/build-librime-deps.sh --all` to refresh static
   dependency prefixes.
2. Use `android/scripts/device-smoke.sh` to install the debug APK on a connected
   Android device or emulator, enable the IME, and print manual smoke steps.
   Optional `--logcat` flag starts a filtered KnowSayin/Rime logcat tail.
3. Smoke fixed non-private input such as `nihao` and `ba ba`.
4. Verify first-run deployment latency, candidate display/selection, commit,
   backspace, enter, CN/EN toggle, optimize, undo, voice, and sensitive-field
   lockout.
5. Additional schemas should follow the same permissive-license rules.

## Device smoke script

`android/scripts/device-smoke.sh` automates device/emulator smoke setup:

- Verifies `adb`, APK existence, and a single connected device.
- Installs the debug APK, enables the IME via `ime enable`, sets it via `ime set`.
- Prints clear manual smoke steps with fixed non-private examples.
- Accepts optional env vars: `ANDROID_HOME`, `APK_PATH`, `IME_COMPONENT`.
- `--logcat` starts an opt-in filtered logcat tail (KnowSayin/Rime generic lines only).
- Fails clearly if no device/emulator is attached.
- Does not capture or print private user text; does not dump broad logcat.

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
