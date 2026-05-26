package com.knowsayin.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ImeLifecycleGuardTest {

    @Test
    fun `input change invalidates previous token`() {
        val guard = ImeLifecycleGuard()
        val firstToken = guard.currentToken()

        guard.markInputChanged()

        assertFalse(guard.isCurrent(firstToken))
        assertTrue(guard.isCurrent(guard.currentToken()))
    }

    @Test
    fun `destroy invalidates all tokens`() {
        val guard = ImeLifecycleGuard()
        val token = guard.currentToken()

        guard.markDestroyed()

        assertFalse(guard.isCurrent(token))
        assertTrue(guard.isDestroyed())
    }
}
