package com.knowsayin.android.rime

interface RimeEngine {

    fun initialize(dataDir: String): Boolean

    fun createSession(): Long

    fun destroySession(sessionId: Long): Boolean

    fun processKey(sessionId: Long, keycode: Int, mask: Int): Boolean

    fun getContext(sessionId: Long): RimeSessionState

    fun getCommit(sessionId: Long): String?

    fun selectCandidate(sessionId: Long, index: Int): Boolean

    fun finalize()
}
