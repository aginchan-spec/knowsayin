package com.knowsayin.android.voice

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log

class VoiceInputManager(private val context: Context) {

    companion object {
        private const val TAG = "VoiceInputManager"
    }

    interface Callback {
        fun onPartialResult(text: String)
        fun onFinalResult(text: String)
        fun onError(error: String)
        fun onReady()
        fun onEndOfSpeech()
    }

    private var recognizer: SpeechRecognizer? = null
    private var callback: Callback? = null
    private var isListening = false

    fun startListening(cb: Callback) {
        callback = cb
        if (recognizer == null) {
            recognizer = createRecognizer()
        }
        val sr = recognizer ?: run {
            cb.onError("SpeechRecognizer not available")
            return
        }

        sr.setRecognitionListener(VoiceListener())
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
        }
        isListening = true
        sr.startListening(intent)
    }

    fun stopListening() {
        isListening = false
        recognizer?.stopListening()
    }

    fun destroy() {
        isListening = false
        recognizer?.destroy()
        recognizer = null
        callback = null
    }

    fun isActive(): Boolean = isListening

    private fun createRecognizer(): SpeechRecognizer? {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            } else {
                SpeechRecognizer.createSpeechRecognizer(context)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create SpeechRecognizer: ${e.message}")
            try {
                SpeechRecognizer.createSpeechRecognizer(context)
            } catch (e2: Exception) {
                Log.e(TAG, "Fallback SpeechRecognizer also failed: ${e2.message}")
                null
            }
        }
    }

    private inner class VoiceListener : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
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
            val msg = when (error) {
                SpeechRecognizer.ERROR_NETWORK -> "Network error"
                SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
                SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                SpeechRecognizer.ERROR_SERVER -> "Server error"
                SpeechRecognizer.ERROR_CLIENT -> "Client error"
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech input"
                SpeechRecognizer.ERROR_NO_MATCH -> "No recognition match"
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Recognizer busy"
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Insufficient permissions"
                else -> "Error $error"
            }
            callback?.onError(msg)
        }

        override fun onResults(results: Bundle?) {
            isListening = false
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            if (!matches.isNullOrEmpty()) {
                callback?.onFinalResult(matches[0])
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            if (!matches.isNullOrEmpty()) {
                callback?.onPartialResult(matches[0])
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}
