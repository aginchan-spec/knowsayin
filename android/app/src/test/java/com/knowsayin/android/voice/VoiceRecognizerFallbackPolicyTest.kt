package com.knowsayin.android.voice

import android.speech.SpeechRecognizer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceRecognizerFallbackPolicyTest {

    @Test
    fun `retries default recognizer for on-device language pack errors`() {
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE,
                defaultRetryAttempted = false,
                recognitionContentSeen = true,
                recognizerReady = true,
            )
        )
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
    }

    @Test
    fun `retries setup style on-device errors only before ready or recognition content`() {
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_CLIENT,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = true,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                defaultRetryAttempted = false,
                recognitionContentSeen = true,
                recognizerReady = false,
            )
        )
    }

    @Test
    fun `does not retry default or already retried recognizers`() {
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.DEFAULT,
                errorCode = SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE,
                defaultRetryAttempted = true,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
    }

    @Test
    fun `does not retry hardware or permission failures`() {
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_AUDIO,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = false,
            )
        )
    }

    @Test
    fun `does not retry default recognizer for ordinary no speech silence after ready`() {
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = true,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = VoiceRecognizerKind.ON_DEVICE,
                errorCode = SpeechRecognizer.ERROR_SPEECH_TIMEOUT,
                defaultRetryAttempted = false,
                recognitionContentSeen = false,
                recognizerReady = true,
            )
        )
    }

    @Test
    fun `restarts listening for silence errors only after recognition content and while requested`() {
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                recognitionContentSeen = true,
            )
        )
        assertTrue(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_SPEECH_TIMEOUT,
                recognitionContentSeen = true,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                recognitionContentSeen = false,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_SPEECH_TIMEOUT,
                recognitionContentSeen = false,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = false,
                errorCode = SpeechRecognizer.ERROR_NO_MATCH,
                recognitionContentSeen = true,
            )
        )
    }

    @Test
    fun `does not restart listening for real recognizer failures`() {
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_AUDIO,
                recognitionContentSeen = true,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS,
                recognitionContentSeen = true,
            )
        )
        assertFalse(
            VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = true,
                errorCode = SpeechRecognizer.ERROR_NETWORK,
                recognitionContentSeen = true,
            )
        )
    }

    @Test
    fun `maps language errors to user visible status text`() {
        assertEquals(
            "Language unavailable",
            VoiceRecognizerFallbackPolicy.errorMessage(SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE)
        )
        assertEquals(
            "Language not supported",
            VoiceRecognizerFallbackPolicy.errorMessage(SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED)
        )
    }
}
