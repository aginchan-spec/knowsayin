package com.knowsayin.android.voice

import org.junit.Assert.assertEquals
import org.junit.Test

class SpaceVoiceHoldPolicyTest {

    @Test
    fun `short release after voice start locks listening`() {
        assertEquals(
            SpaceVoiceReleaseAction.LOCK,
            SpaceVoiceHoldPolicy.releaseAction(0L)
        )
        assertEquals(
            SpaceVoiceReleaseAction.LOCK,
            SpaceVoiceHoldPolicy.releaseAction(599L)
        )
        assertEquals(
            SpaceVoiceReleaseAction.LOCK,
            SpaceVoiceHoldPolicy.releaseAction(600L)
        )
    }

    @Test
    fun `release after hold threshold stops listening`() {
        assertEquals(
            SpaceVoiceReleaseAction.STOP,
            SpaceVoiceHoldPolicy.releaseAction(601L)
        )
    }

    @Test
    fun `negative release duration is treated as immediate release`() {
        assertEquals(
            SpaceVoiceReleaseAction.LOCK,
            SpaceVoiceHoldPolicy.releaseAction(-25L)
        )
    }
}
