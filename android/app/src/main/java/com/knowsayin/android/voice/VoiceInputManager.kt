package com.knowsayin.android.voice

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log

class VoiceInputManager(private val context: Context) {

    companion object {
        private const val TAG = "VoiceInputManager"
        private const val SILENCE_RESTART_DELAY_MS = 120L
    }

    interface Callback {
        fun onPartialResult(text: String)
        fun onFinalResult(text: String)
        fun onError(error: String)
        fun onError(error: String, errorCode: Int) {
            onError(error)
        }
        fun onReady()
        fun onEndOfSpeech()
        fun onStatus(status: String) {}
    }

    private val handler = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var recognizerKind: VoiceRecognizerKind? = null
    private var callback: Callback? = null
    private var activeIntent: Intent? = null
    private var fallbackToDefaultAttempted = false
    private var preferDefaultRecognizer = false
    private var restartOnSilence = false
    private var restartGeneration = 0
    private var recognitionContentSeen = false
    private var recognizerReady = false
    private var isListening = false

    fun startListening(cb: Callback, restartOnSilence: Boolean = false) {
        callback = cb
        this.restartOnSilence = restartOnSilence
        fallbackToDefaultAttempted = false
        recognitionContentSeen = false
        recognizerReady = false
        restartGeneration += 1
        if (recognizer == null) {
            val created = createPreferredRecognizer()
            recognizer = created?.recognizer
            recognizerKind = created?.kind
        }
        val sr = recognizer ?: run {
            cb.onError("SpeechRecognizer not available")
            return
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
        }
        activeIntent = intent
        startRecognizer(sr, intent, cb)
    }

    fun stopListening() {
        isListening = false
        activeIntent = null
        restartOnSilence = false
        recognitionContentSeen = false
        recognizerReady = false
        restartGeneration += 1
        handler.removeCallbacksAndMessages(null)
        recognizer?.stopListening()
    }

    fun cancelListening() {
        isListening = false
        activeIntent = null
        restartOnSilence = false
        recognitionContentSeen = false
        recognizerReady = false
        restartGeneration += 1
        handler.removeCallbacksAndMessages(null)
        recognizer?.cancel()
    }

    fun destroy() {
        isListening = false
        activeIntent = null
        restartOnSilence = false
        recognitionContentSeen = false
        recognizerReady = false
        restartGeneration += 1
        handler.removeCallbacksAndMessages(null)
        recognizer?.destroy()
        recognizer = null
        recognizerKind = null
        callback = null
    }

    fun isActive(): Boolean = isListening

    private data class CreatedRecognizer(
        val recognizer: SpeechRecognizer,
        val kind: VoiceRecognizerKind,
    )

    private fun createPreferredRecognizer(): CreatedRecognizer? {
        if (!preferDefaultRecognizer && isOnDeviceRecognitionAvailable()) {
            createRecognizer(VoiceRecognizerKind.ON_DEVICE)?.let { return it }
        }
        return createRecognizer(VoiceRecognizerKind.DEFAULT)
    }

    private fun createRecognizer(kind: VoiceRecognizerKind): CreatedRecognizer? {
        return try {
            val sr = if (kind == VoiceRecognizerKind.ON_DEVICE) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
                } else {
                    return null
                }
            } else {
                SpeechRecognizer.createSpeechRecognizer(context)
            }
            CreatedRecognizer(sr, kind)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create ${kind.label} SpeechRecognizer: ${e.message}")
            null
        }
    }

    private fun isOnDeviceRecognitionAvailable(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return false
        return try {
            SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check on-device SpeechRecognizer availability: ${e.message}")
            false
        }
    }

    private fun startRecognizer(sr: SpeechRecognizer, intent: Intent, cb: Callback) {
        sr.setRecognitionListener(VoiceListener())
        isListening = true
        try {
            sr.startListening(intent)
        } catch (e: Exception) {
            isListening = false
            Log.e(TAG, "Failed to start ${recognizerKind?.label ?: "unknown"} SpeechRecognizer: ${e.message}")
            if (!retryWithDefaultRecognizer(SpeechRecognizer.ERROR_CLIENT)) {
                activeIntent = null
                cb.onError("Failed to start voice input", SpeechRecognizer.ERROR_CLIENT)
            }
        }
    }

    private fun retryWithDefaultRecognizer(error: Int): Boolean {
        if (!VoiceRecognizerFallbackPolicy.shouldRetryWithDefault(
                recognizerKind = recognizerKind,
                errorCode = error,
                defaultRetryAttempted = fallbackToDefaultAttempted,
                recognitionContentSeen = recognitionContentSeen,
                recognizerReady = recognizerReady,
            )
        ) {
            return false
        }

        val intent = activeIntent ?: return false
        val cb = callback ?: return false
        fallbackToDefaultAttempted = true
        preferDefaultRecognizer = true
        recognitionContentSeen = false
        recognizerReady = false
        isListening = false
        recognizer?.destroy()
        recognizer = null
        recognizerKind = null

        cb.onStatus("using default voice input")
        val created = createRecognizer(VoiceRecognizerKind.DEFAULT) ?: run {
            activeIntent = null
            cb.onError("On-device voice unavailable; default recognizer unavailable")
            return true
        }
        recognizer = created.recognizer
        recognizerKind = created.kind
        startRecognizer(created.recognizer, intent, cb)
        return true
    }

    private fun restartAfterRecoverableSilence(error: Int): Boolean {
        if (!VoiceRecognizerFallbackPolicy.shouldRestartListening(
                restartOnSilence = restartOnSilence,
                errorCode = error,
                recognitionContentSeen = recognitionContentSeen,
            )
        ) {
            return false
        }

        val intent = activeIntent ?: return false
        val cb = callback ?: return false
        val kind = recognizerKind ?: return false
        val generation = restartGeneration
        recognitionContentSeen = false
        recognizerReady = false
        isListening = false
        recognizer?.destroy()
        recognizer = null
        recognizerKind = null

        handler.postDelayed({
            if (generation != restartGeneration ||
                activeIntent == null ||
                callback !== cb
            ) {
                return@postDelayed
            }

            val created = createRecognizer(kind) ?: createPreferredRecognizer()
            if (created == null) {
                activeIntent = null
                cb.onError(VoiceRecognizerFallbackPolicy.errorMessage(error), error)
                return@postDelayed
            }
            recognizer = created.recognizer
            recognizerKind = created.kind
            startRecognizer(created.recognizer, intent, cb)
        }, SILENCE_RESTART_DELAY_MS)
        return true
    }

    private inner class VoiceListener : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            recognizerReady = true
            callback?.onReady()
        }

        override fun onBeginningOfSpeech() {}

        override fun onRmsChanged(rmsdB: Float) {}

        override fun onBufferReceived(buffer: ByteArray?) {}

        override fun onEndOfSpeech() {
            callback?.onEndOfSpeech()
        }

        override fun onError(error: Int) {
            isListening = false
            if (retryWithDefaultRecognizer(error)) {
                return
            }
            if (restartAfterRecoverableSilence(error)) {
                return
            }
            activeIntent = null
            val msg = VoiceRecognizerFallbackPolicy.errorMessage(error)
            callback?.onError(msg, error)
        }

        override fun onResults(results: Bundle?) {
            isListening = false
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull { it.isNotBlank() }
            if (text != null) {
                recognitionContentSeen = true
                activeIntent = null
                callback?.onFinalResult(text)
            } else {
                val error = SpeechRecognizer.ERROR_NO_MATCH
                if (!restartAfterRecoverableSilence(error)) {
                    activeIntent = null
                    callback?.onError(VoiceRecognizerFallbackPolicy.errorMessage(error), error)
                }
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull { it.isNotBlank() }
            if (text != null) {
                recognitionContentSeen = true
                callback?.onPartialResult(text)
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}
