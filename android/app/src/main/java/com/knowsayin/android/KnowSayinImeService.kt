package com.knowsayin.android

import android.Manifest
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager
import android.view.inputmethod.InputMethodSubtype
import androidx.core.content.ContextCompat
import com.knowsayin.android.cloud.CleanResult
import com.knowsayin.android.cloud.KnowSayinCloudClient
import com.knowsayin.android.keyboard.KeyboardView
import com.knowsayin.android.rime.JniRimeEngine
import com.knowsayin.android.rime.RimeEngine
import com.knowsayin.android.rime.StubRimeEngine
import com.knowsayin.android.undo.UndoManager
import com.knowsayin.android.voice.VoiceInputManager
import java.util.Locale

class KnowSayinImeService : android.inputmethodservice.InputMethodService() {

    private lateinit var keyboardView: KeyboardView
    private lateinit var rimeEngine: RimeEngine
    private lateinit var cloudClient: KnowSayinCloudClient
    private lateinit var undoManager: UndoManager
    private lateinit var voiceInputManager: VoiceInputManager
    private lateinit var prefs: SharedPreferences
    private val handler = Handler(Looper.getMainLooper())

    private var rimeSessionId: Long = -1
    private var isChineseMode = true
    private var statusText = ""
    private var isOptimizing = false

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences("knowsayin_prefs", android.content.Context.MODE_PRIVATE)
        initializeRimeEngine()
        cloudClient = KnowSayinCloudClient(prefs)
        undoManager = UndoManager()
        voiceInputManager = VoiceInputManager(this)

        // Ensure we have a cloud session
        if (cloudClient.getSessionToken() == null) {
            cloudClient.createSession()
        }
    }

    override fun onCreateInputView(): android.view.View {
        keyboardView = KeyboardView(this)
        keyboardView.listener = keyboardListener
        keyboardView.isChineseMode = isChineseMode
        keyboardView.statusText = statusText
        clearStatusAfterDelay()
        return keyboardView
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        updateKeyboardState()
    }

    override fun onStartInput(info: EditorInfo?, restarting: Boolean) {
        super.onStartInput(info, restarting)
        updateSensitiveState(info)
    }

    override fun onWindowShown() {
        super.onWindowShown()
        updateKeyboardState()
    }

    private fun updateKeyboardState() {
        keyboardView.isChineseMode = isChineseMode
        keyboardView.composition = ""
        keyboardView.candidates = emptyList()
        keyboardView.statusText = if (isSensitiveField()) getString(R.string.status_skipped_sensitive) else statusText
        keyboardView.invalidate()
    }

    private fun initializeRimeEngine() {
        val nativeEngine = JniRimeEngine(this)
        if (nativeEngine.initialize(filesDir.absolutePath + "/rime")) {
            val sessionId = nativeEngine.createSession()
            if (sessionId > 0) {
                rimeEngine = nativeEngine
                rimeSessionId = sessionId
                return
            }
            nativeEngine.finalize()
        }

        val fallbackEngine = StubRimeEngine()
        fallbackEngine.initialize(filesDir.absolutePath + "/rime")
        rimeEngine = fallbackEngine
        rimeSessionId = fallbackEngine.createSession()
    }

    private var currentInputType: Int = 0

    private fun updateSensitiveState(info: EditorInfo?) {
        currentInputType = info?.inputType ?: 0
        if (isSensitiveField()) {
            statusText = getString(R.string.status_skipped_sensitive)
        } else {
            statusText = ""
        }
    }

    private fun isSensitiveField(): Boolean {
        return SensitiveInputDetector.isSensitive(currentInputType) ||
                SensitiveInputDetector.isFiltered(currentInputType)
    }

    // --- Keyboard listener ---

    private val keyboardListener = object : KeyboardView.OnKeyboardActionListener {

        override fun onKey(key: KeyboardView.Key) {
            when (key.type) {
                KeyboardView.KeyType.CHARACTER -> handleCharacterKey(key.code)
                KeyboardView.KeyType.SPACE -> handleCharacterKey(' '.code)
                KeyboardView.KeyType.BACKSPACE -> handleBackspace()
                KeyboardView.KeyType.ENTER -> handleEnter()
                KeyboardView.KeyType.COMMA -> handleCharacterKey(','.code)
                KeyboardView.KeyType.PERIOD -> handleCharacterKey('.'.code)
                KeyboardView.KeyType.SHIFT -> {
                    keyboardView.isUpperCase = !keyboardView.isUpperCase
                    keyboardView.invalidate()
                }
                KeyboardView.KeyType.SYMBOL -> {
                    // TODO: symbol keyboard layer
                    commitText("?")
                }
                else -> {}
            }
        }

        override fun onCandidateSelected(index: Int) {
            if (isChineseMode) {
                rimeEngine.selectCandidate(rimeSessionId, index)
                flushRimeCommit()
                flushRimeContext()
            }
        }

        override fun onToolbarAction(action: KeyboardView.ToolbarAction) {
            when (action) {
                KeyboardView.ToolbarAction.OPTIMIZE -> performOptimize()
                KeyboardView.ToolbarAction.MICROPHONE -> startVoiceInput()
                KeyboardView.ToolbarAction.UNDO -> performUndo()
                KeyboardView.ToolbarAction.TOGGLE_CN_EN -> toggleChineseMode()
                KeyboardView.ToolbarAction.SETTINGS -> openSettings()
                KeyboardView.ToolbarAction.SWITCH_IME -> switchToNextIme()
            }
        }
    }

    // --- Key handling ---

    private fun handleCharacterKey(code: Int) {
        val ic = currentInputConnection ?: return

        if (isChineseMode) {
            rimeEngine.processKey(rimeSessionId, code, 0)
            flushRimeCommit()
            flushRimeContext()
        } else {
            val text = code.toChar().let {
                if (keyboardView.isUpperCase) it.uppercaseChar() else it
            }
            commitText(text.toString())

            // Auto lowercase after one uppercase character
            if (keyboardView.isUpperCase) {
                keyboardView.isUpperCase = false
                keyboardView.invalidate()
            }
        }
    }

    private fun handleBackspace() {
        val ic = currentInputConnection ?: return
        val state = rimeEngine.getContext(rimeSessionId)
        if (state.isComposing && state.composition.isNotEmpty()) {
            // Send backspace to rime
            rimeEngine.processKey(rimeSessionId, KeyEvent.KEYCODE_DEL, 0)
            flushRimeCommit()
            flushRimeContext()
        } else {
            ic.deleteSurroundingText(1, 0)
        }
    }

    private fun handleEnter() {
        if (isChineseMode) {
            val state = rimeEngine.getContext(rimeSessionId)
            if (state.isComposing && state.composition.isNotEmpty()) {
                if (!rimeEngine.processKey(rimeSessionId, KeyEvent.KEYCODE_ENTER, 0)) {
                    commitText(state.composition)
                    rimeEngine.selectCandidate(rimeSessionId, -1)
                }
                flushRimeCommit()
                flushRimeContext()
            }
        }
        commitText("\n")
    }

    private fun flushRimeContext() {
        val state = rimeEngine.getContext(rimeSessionId)
        val ic = currentInputConnection

        if (state.isComposing && state.composition.isNotEmpty() && ic != null) {
            ic.setComposingText(state.composition, 1)
        } else {
            ic?.finishComposingText()
        }

        keyboardView.composition = if (state.isComposing) state.composition else ""
        keyboardView.candidates = state.candidates.map { it.text }
        keyboardView.invalidate()
    }

    private fun flushRimeCommit() {
        val commit = rimeEngine.getCommit(rimeSessionId)
        if (commit != null) {
            commitText(commit)
        }
    }

    private fun commitText(text: String) {
        val ic = currentInputConnection ?: return
        ic.commitText(text, 1)
    }

    // --- Toolbar actions ---

    private fun performOptimize() {
        if (isOptimizing) return
        if (isSensitiveField()) {
            setStatus(getString(R.string.status_skipped_sensitive))
            return
        }

        val ic = currentInputConnection ?: return
        val plan = TextReplacementPlanner.plan(ic)
        if (plan == null || plan.textToClean.isEmpty()) {
            setStatus("no text")
            return
        }

        isOptimizing = true
        setStatus(getString(R.string.status_optimizing))

        Thread {
            val result = cloudClient.clean(plan.textToClean)
            handler.post {
                isOptimizing = false
                when (result) {
                    is CleanResult.Success -> {
                        val cleaned = result.text
                        val replIc = currentInputConnection
                        if (replIc != null) {
                            if (plan.isSelectedText) {
                                replIc.commitText(cleaned, 1)
                            } else {
                                replIc.deleteSurroundingText(plan.beforeLength, 0)
                                replIc.commitText(cleaned, 1)
                            }
                        }
                        undoManager.store(plan.textToClean, cleaned)
                        setStatus(getString(R.string.status_done))
                    }
                    is CleanResult.QuotaEmpty -> {
                        setStatus(getString(R.string.status_quota_empty))
                    }
                    is CleanResult.Error -> {
                        setStatus(getString(R.string.status_cloud_error))
                    }
                }
                clearStatusAfterDelay()
            }
        }.start()
    }

    private fun performUndo() {
        if (!undoManager.hasUndo()) {
            setStatus("nothing to undo")
            clearStatusAfterDelay()
            return
        }

        val entry = undoManager.pop() ?: return
        val ic = currentInputConnection ?: return
        // Get text before cursor; find and replace the 'after' text
        val beforeText = ic.getTextBeforeCursor(500, 0) ?: ""
        if (beforeText.endsWith(entry.after)) {
            ic.deleteSurroundingText(entry.after.length, 0)
        }
        ic.commitText(entry.before, 1)
        setStatus("undone")
        clearStatusAfterDelay()
    }

    private fun toggleChineseMode() {
        isChineseMode = !isChineseMode
        keyboardView.isChineseMode = isChineseMode
        keyboardView.candidates = emptyList()
        keyboardView.composition = ""
        keyboardView.invalidate()

        // Switch IME subtype for system language indicator
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val subtypes = imm.getEnabledInputMethodSubtypeList(
            imm.getInputMethodList().find { it.serviceName == this.javaClass.name }, true
        )
        // Toggle between first two subtypes or just notify
        setStatus(if (isChineseMode) "中文" else "EN")
        clearStatusAfterDelay()
    }

    private fun openSettings() {
        val intent = android.content.Intent(this, SettingsActivity::class.java).apply {
            addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
    }

    private fun switchToNextIme() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        // Try to switch to next IME; on API 28+ we can use switchToNextInputMethod
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            switchToNextInputMethod(false)
        } else {
            imm.showInputMethodPicker()
        }
    }

    // --- Voice input ---

    private fun startVoiceInput() {
        if (isSensitiveField()) {
            setStatus(getString(R.string.status_skipped_sensitive))
            clearStatusAfterDelay()
            return
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            setStatus("mic permission needed")
            clearStatusAfterDelay()
            return
        }

        setStatus("listening…")
        voiceInputManager.startListening(object : VoiceInputManager.Callback {
            override fun onPartialResult(text: String) {
                setStatus("…")
            }

            override fun onFinalResult(text: String) {
                setStatus("")
                commitText(text)
            }

            override fun onError(error: String) {
                setStatus("voice: $error")
                clearStatusAfterDelay()
            }

            override fun onReady() {
                setStatus("speak now")
            }

            override fun onEndOfSpeech() {
                setStatus("processing…")
            }
        })
    }

    // --- Status helpers ---

    private fun setStatus(text: String) {
        statusText = text
        keyboardView.statusText = text
        keyboardView.invalidate()
    }

    private fun clearStatusAfterDelay() {
        handler.postDelayed({
            if (statusText.isNotEmpty() && !isOptimizing) {
                setStatus("")
            }
        }, 2500)
    }

    override fun onDestroy() {
        voiceInputManager.destroy()
        rimeEngine.destroySession(rimeSessionId)
        rimeEngine.finalize()
        super.onDestroy()
    }
}
