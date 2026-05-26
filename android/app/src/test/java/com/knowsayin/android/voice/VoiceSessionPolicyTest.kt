package com.knowsayin.android.voice

import org.junit.Assert.assertEquals
import org.junit.Test

class VoiceSessionPolicyTest {

    @Test
    fun `hold and locked final results restart current voice session`() {
        assertEquals(
            VoiceFinalResultAction.RESTART,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.HOLD,
                isCurrentRequest = true,
            )
        )
        assertEquals(
            VoiceFinalResultAction.RESTART,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.LOCKED,
                isCurrentRequest = true,
            )
        )
    }

    @Test
    fun `delayed final result recheck honors release state changes`() {
        assertEquals(
            VoiceFinalResultAction.RESTART,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.HOLD,
                isCurrentRequest = true,
            )
        )
        assertEquals(
            VoiceFinalResultAction.RESTART,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.LOCKED,
                isCurrentRequest = true,
            )
        )
        assertEquals(
            VoiceFinalResultAction.FINISH,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.STOPPING,
                isCurrentRequest = true,
            )
        )
        assertEquals(
            VoiceFinalResultAction.IGNORE,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.NONE,
                isCurrentRequest = true,
            )
        )
    }

    @Test
    fun `stopping final result finishes instead of restarting`() {
        assertEquals(
            VoiceFinalResultAction.FINISH,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.STOPPING,
                isCurrentRequest = true,
            )
        )
    }

    @Test
    fun `none or stale final result is ignored`() {
        assertEquals(
            VoiceFinalResultAction.IGNORE,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.NONE,
                isCurrentRequest = true,
            )
        )
        assertEquals(
            VoiceFinalResultAction.IGNORE,
            VoiceSessionPolicy.finalResultAction(
                mode = VoiceSessionMode.HOLD,
                isCurrentRequest = false,
            )
        )
    }
}
