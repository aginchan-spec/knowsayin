package com.knowsayin.android.voice

internal enum class VoiceSessionMode {
    NONE,
    HOLD,
    LOCKED,
    STOPPING,
}

internal enum class VoiceFinalResultAction {
    IGNORE,
    FINISH,
    RESTART,
}

internal object VoiceSessionPolicy {
    fun finalResultAction(
        mode: VoiceSessionMode,
        isCurrentRequest: Boolean,
    ): VoiceFinalResultAction {
        if (!isCurrentRequest) return VoiceFinalResultAction.IGNORE
        return when (mode) {
            VoiceSessionMode.HOLD,
            VoiceSessionMode.LOCKED -> VoiceFinalResultAction.RESTART
            VoiceSessionMode.STOPPING -> VoiceFinalResultAction.FINISH
            VoiceSessionMode.NONE -> VoiceFinalResultAction.IGNORE
        }
    }
}
