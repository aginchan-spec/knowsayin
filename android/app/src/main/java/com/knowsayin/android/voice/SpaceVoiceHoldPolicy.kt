package com.knowsayin.android.voice

internal enum class SpaceVoiceReleaseAction {
    LOCK,
    STOP,
}

internal object SpaceVoiceHoldPolicy {
    const val DEFAULT_LOCK_THRESHOLD_MS = 600L

    fun releaseAction(
        heldAfterStartMs: Long,
        lockThresholdMs: Long = DEFAULT_LOCK_THRESHOLD_MS,
    ): SpaceVoiceReleaseAction {
        val heldMs = heldAfterStartMs.coerceAtLeast(0L)
        return if (heldMs <= lockThresholdMs) {
            SpaceVoiceReleaseAction.LOCK
        } else {
            SpaceVoiceReleaseAction.STOP
        }
    }
}
