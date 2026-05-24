package com.knowsayin.android.rime

object RimeJniBridge {

    private var isLoaded = false

    fun ensureLoaded(): Boolean {
        if (isLoaded) return true
        return try {
            System.loadLibrary("knowsayin-rime")
            isLoaded = true
            true
        } catch (e: UnsatisfiedLinkError) {
            false
        }
    }

    // --- Diagnostics ---

    @JvmStatic
    external fun nativeGetVersion(): String

    @JvmStatic
    external fun nativeGetBuildInfo(): String

    // --- Lifecycle ---

    @JvmStatic
    external fun nativeInitialize(dataDir: String, sharedDataDir: String): Boolean

    @JvmStatic
    external fun nativeFinalize(): Boolean

    // --- Session ---

    @JvmStatic
    external fun nativeCreateSession(): Long

    @JvmStatic
    external fun nativeDestroySession(sessionId: Long): Boolean

    @JvmStatic
    external fun nativeSessionExists(sessionId: Long): Boolean

    // --- Input ---

    @JvmStatic
    external fun nativeProcessKey(sessionId: Long, keycode: Int, mask: Int): Boolean

    @JvmStatic
    external fun nativeSimulateKeySequence(sessionId: Long, sequence: String): Boolean

    // --- Context ---

    @JvmStatic
    external fun nativeGetContext(sessionId: Long): String

    @JvmStatic
    external fun nativeGetCommit(sessionId: Long): String?

    // --- Candidate ---

    @JvmStatic
    external fun nativeSelectCandidate(sessionId: Long, index: Int): Boolean

    @JvmStatic
    external fun nativeHighlightCandidate(sessionId: Long, index: Int): Boolean

    // --- Config ---

    @JvmStatic
    external fun nativeSetOption(sessionId: Long, option: String, value: Boolean): Boolean

    @JvmStatic
    external fun nativeGetProperty(name: String): String?

    @JvmStatic
    external fun nativeLoadSchema(schemaId: String): Boolean

    @JvmStatic
    external fun nativeConfigure(key: String, value: String): Boolean

    // --- Maintenance ---

    @JvmStatic
    external fun nativeStartMaintenance(fullCheck: Boolean): Boolean
}
