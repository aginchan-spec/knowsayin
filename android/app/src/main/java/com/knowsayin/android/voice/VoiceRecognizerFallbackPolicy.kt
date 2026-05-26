package com.knowsayin.android.voice

import android.speech.SpeechRecognizer

internal enum class VoiceRecognizerKind(val label: String) {
    ON_DEVICE("on-device"),
    DEFAULT("default"),
}

internal object VoiceRecognizerFallbackPolicy {

    fun shouldRetryWithDefault(
        recognizerKind: VoiceRecognizerKind?,
        errorCode: Int,
        defaultRetryAttempted: Boolean,
        recognitionContentSeen: Boolean,
        recognizerReady: Boolean,
    ): Boolean {
        if (recognizerKind != VoiceRecognizerKind.ON_DEVICE || defaultRetryAttempted) {
            return false
        }
        return isLanguagePackError(errorCode) ||
                (!recognitionContentSeen && !recognizerReady && isSetupError(errorCode))
    }

    fun shouldRestartListening(
        restartOnSilence: Boolean,
        errorCode: Int,
        recognitionContentSeen: Boolean,
    ): Boolean {
        return restartOnSilence && recognitionContentSeen && isRecoverableSilenceError(errorCode)
    }

    fun isRecoverableSilenceError(errorCode: Int): Boolean {
        return errorCode == SpeechRecognizer.ERROR_NO_MATCH ||
                errorCode == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
    }

    fun errorMessage(error: Int): String {
        return when (error) {
            SpeechRecognizer.ERROR_NETWORK -> "Network error"
            SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
            SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
            SpeechRecognizer.ERROR_SERVER -> "Server error"
            SpeechRecognizer.ERROR_CLIENT -> "Client error"
            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech input"
            SpeechRecognizer.ERROR_NO_MATCH -> "No recognition match"
            SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Recognizer busy"
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Insufficient permissions"
            SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED -> "Language not supported"
            SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "Language unavailable"
            else -> "Error $error"
        }
    }

    private fun isLanguagePackError(error: Int): Boolean {
        return error == SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED ||
                error == SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE
    }

    private fun isSetupError(error: Int): Boolean {
        return error == SpeechRecognizer.ERROR_CLIENT ||
                error == SpeechRecognizer.ERROR_SERVER ||
                error == SpeechRecognizer.ERROR_NO_MATCH ||
                error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT
    }
}
