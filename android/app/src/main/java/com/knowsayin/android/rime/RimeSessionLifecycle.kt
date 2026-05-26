package com.knowsayin.android.rime

object RimeSessionLifecycle {
    const val NO_SESSION: Long = -1L

    fun createSession(engine: RimeEngine): Long {
        val nextSessionId = engine.createSession()
        return if (nextSessionId > 0) nextSessionId else NO_SESSION
    }

    fun destroySession(engine: RimeEngine, currentSessionId: Long): Long {
        if (currentSessionId > 0) {
            engine.destroySession(currentSessionId)
        }
        return NO_SESSION
    }

    fun resetSession(engine: RimeEngine, currentSessionId: Long): Long {
        destroySession(engine, currentSessionId)
        return createSession(engine)
    }
}
