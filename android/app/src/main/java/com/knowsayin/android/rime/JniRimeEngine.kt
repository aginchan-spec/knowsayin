package com.knowsayin.android.rime

import android.content.Context

class JniRimeEngine(context: Context) : RimeEngine {

    private val appContext = context.applicationContext
    private var initialized = false

    override fun initialize(dataDir: String): Boolean {
        if (initialized) return true

        return try {
            if (!RimeJniBridge.ensureLoaded()) return false
            val (sharedDir, userDir) = RimeAssetManager.extractIfNeeded(appContext)
            if (!RimeJniBridge.nativeInitialize(userDir.absolutePath, sharedDir.absolutePath)) {
                return false
            }
            if (!RimeJniBridge.nativeLoadSchema(DEFAULT_SCHEMA)) {
                RimeJniBridge.nativeFinalize()
                return false
            }
            initialized = true
            true
        } catch (_: Throwable) {
            false
        }
    }

    override fun createSession(): Long {
        if (!initialized) return 0L

        return try {
            val sessionId = RimeJniBridge.nativeCreateSession()
            if (sessionId > 0 && RimeJniBridge.nativeSessionExists(sessionId)) {
                sessionId
            } else {
                0L
            }
        } catch (_: Throwable) {
            0L
        }
    }

    override fun destroySession(sessionId: Long): Boolean {
        if (!initialized || sessionId <= 0) return false

        return try {
            RimeJniBridge.nativeDestroySession(sessionId)
        } catch (_: Throwable) {
            false
        }
    }

    override fun processKey(sessionId: Long, keycode: Int, mask: Int): Boolean {
        if (!initialized || sessionId <= 0) return false

        return try {
            RimeJniBridge.nativeProcessKey(sessionId, keycode, mask)
        } catch (_: Throwable) {
            false
        }
    }

    override fun getContext(sessionId: Long): RimeSessionState {
        if (!initialized || sessionId <= 0) return RimeSessionState()

        return try {
            RimeContextJsonParser.parse(RimeJniBridge.nativeGetContext(sessionId))
        } catch (_: Throwable) {
            RimeSessionState()
        }
    }

    override fun getCommit(sessionId: Long): String? {
        if (!initialized || sessionId <= 0) return null

        return try {
            RimeJniBridge.nativeGetCommit(sessionId)
        } catch (_: Throwable) {
            null
        }
    }

    override fun selectCandidate(sessionId: Long, index: Int): Boolean {
        if (!initialized || sessionId <= 0) return false

        return try {
            RimeJniBridge.nativeSelectCandidate(sessionId, index)
        } catch (_: Throwable) {
            false
        }
    }

    override fun finalize() {
        if (!initialized) return

        try {
            RimeJniBridge.nativeFinalize()
        } catch (_: Throwable) {
            // Keep IME shutdown non-fatal.
        } finally {
            initialized = false
        }
    }

    companion object {
        const val DEFAULT_SCHEMA = "knowsayin_pinyin"
    }
}
