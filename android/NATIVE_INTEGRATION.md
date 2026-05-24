# Native librime Integration

Current state: **stub only**. The `StubRimeEngine` echoes typed pinyin and returns
simple hardcoded candidates for demo/development. It does not link native librime.

## Integration plan

When ready to integrate the real librime engine:

1. Install Android NDK (r26+) via sdkmanager.
2. Add CMake externalNativeBuild to app/build.gradle.kts.
3. Cross-compile librime dependencies for arm64-v8a + armeabi-v7a:
   - Boost (filesystem, locale, regex)
   - OpenCC (Apache-2.0)
   - yaml-cpp
   - LevelDB + snappy
   - marisa-trie
   - darts-clone (BSD, bundled in librime)
4. Build librime.so (BSD 3-Clause). Exclude librime-octagram (GPL-3.0-only).
5. Replace StubRimeEngine with JNIRimeEngine calling into native-lib.cpp.

## License safety

- librime core: BSD 3-Clause — safe for proprietary/commercial use.
- rime-pinyin-simp dictionary: Apache-2.0 — safe to bundle.
  (Derived from AOSP PinyinIME; see rime report for details.)
- All schemas must be written from scratch (KnowSayin-owned).
- Do NOT bundle: GPL schemas (brise, rime-ice, oh-my-rime),
  librime-octagram (GPL-3.0-only), or Trime source code (GPL-3.0).

## Reference (architecture only — do not copy code)

- fcitx5-android: clean Kotlin/CMake JNI bridge pattern.
- AOSP LatinIME: InputMethodService lifecycle reference.
- librime API: https://github.com/rime/librime

Full integration report: MemoryBank/reports/active/knowsayin/rime.md
