package com.knowsayin.android.rime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RimeSessionLifecycleTest {

    @Test
    fun `reset destroys stale session and creates empty replacement`() {
        val engine = StubRimeEngine()
        assertTrue(engine.initialize("/tmp/rime"))
        val staleSessionId = engine.createSession()
        "shi".forEach { char -> engine.processKey(staleSessionId, char.code, 0) }
        assertTrue(engine.getContext(staleSessionId).isComposing)

        val nextSessionId = RimeSessionLifecycle.resetSession(engine, staleSessionId)

        assertNotEquals(staleSessionId, nextSessionId)
        assertIdle(engine.getContext(staleSessionId))
        assertIdle(engine.getContext(nextSessionId))
    }

    @Test
    fun `reset handles missing current session`() {
        val engine = StubRimeEngine()
        assertTrue(engine.initialize("/tmp/rime"))

        val sessionId = RimeSessionLifecycle.resetSession(engine, RimeSessionLifecycle.NO_SESSION)

        assertTrue(sessionId > 0)
        assertIdle(engine.getContext(sessionId))
    }

    @Test
    fun `destroy clears current session without creating replacement`() {
        val engine = CountingRimeEngine()
        assertTrue(engine.initialize("/tmp/rime"))
        val staleSessionId = engine.createSession()

        val result = RimeSessionLifecycle.destroySession(engine, staleSessionId)

        assertEquals(RimeSessionLifecycle.NO_SESSION, result)
        assertEquals(1, engine.createCalls)
        assertEquals(listOf(staleSessionId), engine.destroyedSessions)
    }

    private fun assertIdle(state: RimeSessionState) {
        assertFalse(state.isComposing)
        assertEquals("", state.composition)
        assertEquals(emptyList<RimeCandidate>(), state.candidates)
    }

    private class CountingRimeEngine : RimeEngine {
        var createCalls = 0
        private var nextSessionId = 1L
        val destroyedSessions = mutableListOf<Long>()

        override fun initialize(dataDir: String): Boolean = true

        override fun createSession(): Long {
            createCalls += 1
            return nextSessionId++
        }

        override fun destroySession(sessionId: Long): Boolean {
            destroyedSessions += sessionId
            return true
        }

        override fun processKey(sessionId: Long, keycode: Int, mask: Int): Boolean = true

        override fun getContext(sessionId: Long): RimeSessionState = RimeSessionState()

        override fun getCommit(sessionId: Long): String? = null

        override fun selectCandidate(sessionId: Long, index: Int): Boolean = true

        override fun finalize() = Unit
    }
}
