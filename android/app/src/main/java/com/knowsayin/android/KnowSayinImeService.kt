package com.knowsayin.android

import android.Manifest
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.view.inputmethod.InputMethodManager
import androidx.core.content.ContextCompat
import com.knowsayin.android.cloud.CleanResult
import com.knowsayin.android.cloud.KnowSayinCloudClient
import com.knowsayin.android.keyboard.KeyboardView
import com.knowsayin.android.rime.JniRimeEngine
import com.knowsayin.android.rime.RimeCandidatePageDirection
import com.knowsayin.android.rime.RimeCandidatePaging
import com.knowsayin.android.rime.RimeEngine
import com.knowsayin.android.rime.RimeSessionState
import com.knowsayin.android.rime.RimeSessionLifecycle
import com.knowsayin.android.rime.SharedPreferencesStubCandidateRanker
import com.knowsayin.android.rime.StubRimeEngine
import com.knowsayin.android.undo.UndoManager
import com.knowsayin.android.voice.SpaceVoiceHoldPolicy
import com.knowsayin.android.voice.SpaceVoiceReleaseAction
import com.knowsayin.android.voice.VoiceFinalResultAction
import com.knowsayin.android.voice.VoiceInputManager
import com.knowsayin.android.voice.VoiceRecognizerFallbackPolicy
import com.knowsayin.android.voice.VoiceSessionMode
import com.knowsayin.android.voice.VoiceSessionPolicy

class KnowSayinImeService : android.inputmethodservice.InputMethodService() {
    private companion object {
        private const val VOICE_FINAL_RESTART_DELAY_MS = 120L
    }

    private lateinit var keyboardView: KeyboardView
    private lateinit var rimeEngine: RimeEngine
    private lateinit var cloudClient: KnowSayinCloudClient
    private lateinit var undoManager: UndoManager
    private lateinit var voiceInputManager: VoiceInputManager
    private lateinit var prefs: SharedPreferences
    private val handler = Handler(Looper.getMainLooper())
    private val lifecycleGuard = ImeLifecycleGuard()
    private val editorCompositionTracker = EditorCompositionTracker()

    private var rimeSessionId: Long = RimeSessionLifecycle.NO_SESSION
    private var isChineseMode = true
    private var statusText = ""
    private var isOptimizing = false
    private var optimizeRequestId = 0
    private var voiceRequestId = 0
    private var voiceSessionMode = VoiceSessionMode.NONE
    private var hasVoiceComposingText = false

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences("knowsayin_prefs", android.content.Context.MODE_PRIVATE)
        initializeRimeEngine()
        cloudClient = KnowSayinCloudClient(prefs)
        undoManager = UndoManager()
        voiceInputManager = VoiceInputManager(this)
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
        markInputLifecycleChanged()
        updateSensitiveState(info)
        clearTransientRimeState(recreateSession = false, destroySession = true)
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        cancelVoiceSessionForLifecycle()
        clearTransientRimeState(recreateSession = false, destroySession = true)
        super.onFinishInputView(finishingInput)
    }

    override fun onFinishInput() {
        clearTransientRimeState(recreateSession = false, destroySession = true)
        markInputLifecycleChanged()
        currentInputType = 0
        currentImeAction = EditorInfo.IME_ACTION_UNSPECIFIED
        currentEditorActionId = 0
        statusText = ""
        super.onFinishInput()
    }

    override fun onWindowShown() {
        super.onWindowShown()
        updateKeyboardState()
    }

    private fun updateKeyboardState() {
        if (!::keyboardView.isInitialized) return
        keyboardView.isChineseMode = isChineseMode
        clearKeyboardRimeState(invalidate = false)
        keyboardView.statusText = if (isSensitiveField()) getString(R.string.status_skipped_sensitive) else statusText
        keyboardView.invalidate()
    }

    private fun clearTransientRimeState(
        recreateSession: Boolean,
        destroySession: Boolean = false
    ) {
        clearEditorComposition()
        if (::rimeEngine.isInitialized) {
            rimeSessionId = when {
                destroySession -> RimeSessionLifecycle.destroySession(rimeEngine, rimeSessionId)
                recreateSession -> RimeSessionLifecycle.resetSession(rimeEngine, rimeSessionId)
                else -> rimeSessionId
            }
        }
        clearKeyboardRimeState()
    }

    private fun clearKeyboardRimeState(invalidate: Boolean = true) {
        if (!::keyboardView.isInitialized) return
        keyboardView.composition = ""
        keyboardView.candidates = emptyList()
        keyboardView.highlightedCandidateIndex = 0
        keyboardView.canPageBackward = false
        keyboardView.canPageForward = false
        if (invalidate) {
            keyboardView.invalidate()
        }
    }

    private fun markInputLifecycleChanged() {
        lifecycleGuard.markInputChanged()
        editorCompositionTracker.markInputLifecycleChanged()
        optimizeRequestId += 1
        isOptimizing = false
        if (::undoManager.isInitialized) {
            undoManager.clear()
        }
        cancelVoiceSessionForLifecycle()
    }

    private fun initializeRimeEngine() {
        val nativeEngine = JniRimeEngine(this)
        if (nativeEngine.initialize(filesDir.absolutePath + "/rime")) {
            val sessionId = nativeEngine.createSession()
            if (sessionId > 0) {
                nativeEngine.destroySession(sessionId)
                rimeEngine = nativeEngine
                rimeSessionId = RimeSessionLifecycle.NO_SESSION
                return
            }
            nativeEngine.finalize()
        }

        val fallbackEngine = StubRimeEngine(
            context = this,
            userRanker = SharedPreferencesStubCandidateRanker(prefs)
        )
        fallbackEngine.initialize(filesDir.absolutePath + "/rime")
        rimeEngine = fallbackEngine
        rimeSessionId = RimeSessionLifecycle.NO_SESSION
    }

    private fun ensureRimeSession(): Boolean {
        if (!::rimeEngine.isInitialized) return false
        if (rimeSessionId > 0) return true
        rimeSessionId = RimeSessionLifecycle.createSession(rimeEngine)
        return rimeSessionId > 0
    }

    private var currentInputType: Int = 0
    private var currentImeAction: Int = EditorInfo.IME_ACTION_UNSPECIFIED
    private var currentEditorActionId: Int = 0

    private fun updateSensitiveState(info: EditorInfo?) {
        currentInputType = info?.inputType ?: 0
        currentImeAction = info?.imeOptions?.and(EditorInfo.IME_MASK_ACTION)
            ?: EditorInfo.IME_ACTION_UNSPECIFIED
        currentEditorActionId = info?.actionId ?: 0
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
            stopVoiceBeforeUserAction()
            when (key.type) {
                KeyboardView.KeyType.CHARACTER -> handleCharacterKey(key.code)
                KeyboardView.KeyType.TEXT -> handleTextKey(key.output ?: key.label)
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
                    keyboardView.isSymbolMode = true
                    keyboardView.invalidate()
                }
                KeyboardView.KeyType.ALPHABET -> {
                    keyboardView.isSymbolMode = false
                    keyboardView.invalidate()
                }
                KeyboardView.KeyType.SYMBOL_PAGE -> {
                    keyboardView.symbolPage = (keyboardView.symbolPage + 1) % 2
                    keyboardView.invalidate()
                }
                KeyboardView.KeyType.TOGGLE_CN_EN -> {
                    toggleChineseMode()
                }
            }
        }

        override fun onCandidateSelected(index: Int) {
            stopVoiceBeforeUserAction()
            if (isChineseMode && !isSensitiveField() && ensureRimeSession()) {
                rimeEngine.selectCandidate(rimeSessionId, index)
                flushRimeCommit()
                flushRimeContext()
            }
        }

        override fun onCandidatePage(forward: Boolean) {
            stopVoiceBeforeUserAction()
            if (!isChineseMode || isSensitiveField() || !ensureRimeSession()) return

            val direction = if (forward) {
                RimeCandidatePageDirection.NEXT
            } else {
                RimeCandidatePageDirection.PREVIOUS
            }
            val state = rimeEngine.getContext(rimeSessionId)
            if (!RimeCandidatePaging.canPage(state, direction)) return

            rimeEngine.processKey(rimeSessionId, direction.keyCode, 0)
            flushRimeCommit()
            flushRimeContext()
        }

        override fun onToolbarAction(action: KeyboardView.ToolbarAction) {
            stopVoiceBeforeUserAction()
            when (action) {
                KeyboardView.ToolbarAction.OPTIMIZE -> performOptimize()
                KeyboardView.ToolbarAction.MICROPHONE -> startVoiceInput(VoiceSessionMode.LOCKED)
                KeyboardView.ToolbarAction.UNDO -> performUndo()
                KeyboardView.ToolbarAction.TOGGLE_CN_EN -> toggleChineseMode()
                KeyboardView.ToolbarAction.SETTINGS -> openSettings()
                KeyboardView.ToolbarAction.HIDE_KEYBOARD -> hideKeyboard()
                KeyboardView.ToolbarAction.SWITCH_IME -> switchToNextIme()
                KeyboardView.ToolbarAction.SEND -> handleSendAction()
                KeyboardView.ToolbarAction.CLEAR_COMPOSITION -> clearComposition()
                KeyboardView.ToolbarAction.MORE,
                KeyboardView.ToolbarAction.EMOJI -> Unit
            }
        }

        override fun onSpaceVoiceHoldStarted() {
            startVoiceInput(VoiceSessionMode.HOLD)
        }

        override fun onSpaceVoiceHoldReleased(heldAfterStartMs: Long) {
            handleSpaceVoiceHoldReleased(heldAfterStartMs)
        }

        override fun onSpaceVoiceHoldCancelled() {
            if (voiceSessionMode == VoiceSessionMode.HOLD) {
                cancelVoiceSession(finalizePartial = true)
            }
        }
    }

    // --- Key handling ---

    private fun handleCharacterKey(code: Int) {
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
            commitRawCharacter(code)
            return
        }

        if (isChineseMode && ensureRimeSession()) {
            rimeEngine.processKey(rimeSessionId, code, 0)
            flushRimeCommit()
            flushRimeContext()
        } else {
            commitRawCharacter(code)
        }
    }

    private fun handleTextKey(text: String) {
        if (text.isEmpty()) return
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
        } else {
            resolveActiveRimeComposition()
        }
        commitText(text)
    }

    private fun handleBackspace() {
        val ic = currentInputConnection ?: return
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
            ic.deleteSurroundingText(1, 0)
            return
        }

        val state = if (isChineseMode && ensureRimeSession()) {
            rimeEngine.getContext(rimeSessionId)
        } else {
            null
        }
        if (state != null && state.isComposing && state.composition.isNotEmpty()) {
            // Send backspace to rime
            rimeEngine.processKey(rimeSessionId, KeyEvent.KEYCODE_DEL, 0)
            flushRimeCommit()
            flushRimeContext()
        } else {
            ic.deleteSurroundingText(1, 0)
        }
    }

    private fun handleEnter() {
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
            commitText("\n")
            return
        }

        resolveActiveRimeComposition()
        commitText("\n")
    }

    private fun handleSendAction() {
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
        } else {
            resolveActiveRimeComposition()
        }

        if (performEditorActionIfAvailable()) return
        commitText("\n")
    }

    private fun activeRimeState(): RimeSessionState? {
        if (isSensitiveField() || !isChineseMode || rimeSessionId <= 0 || !::rimeEngine.isInitialized) {
            return null
        }
        val state = rimeEngine.getContext(rimeSessionId)
        val hasVisibleState = state.isComposing ||
            state.composition.isNotEmpty() ||
            state.candidates.isNotEmpty()
        return if (hasVisibleState) state else null
    }

    private fun resolveActiveRimeComposition(): Boolean {
        val state = activeRimeState() ?: return false

        if (state.candidates.isNotEmpty()) {
            val index = state.highlightedIndex.coerceIn(0, state.candidates.lastIndex)
            val fallbackText = state.candidates[index].text
            val selected = rimeEngine.selectCandidate(rimeSessionId, index)
            val committed = if (selected) flushRimeCommit() else false
            if (!committed) {
                commitText(fallbackText)
            }
        } else if (state.composition.isNotEmpty()) {
            commitText(state.composition)
        }

        finishEditorCompositionAfterCommit()
        if (::rimeEngine.isInitialized && rimeSessionId > 0) {
            rimeSessionId = RimeSessionLifecycle.destroySession(rimeEngine, rimeSessionId)
        }
        clearKeyboardRimeState()
        return true
    }

    private fun performEditorActionIfAvailable(): Boolean {
        val action = currentEditorAction()
        if (action == EditorInfo.IME_ACTION_UNSPECIFIED ||
            action == EditorInfo.IME_ACTION_NONE
        ) {
            return false
        }
        currentInputConnection?.performEditorAction(action)
        return true
    }

    private fun currentEditorAction(): Int {
        return when (currentImeAction) {
            EditorInfo.IME_ACTION_SEND,
            EditorInfo.IME_ACTION_DONE,
            EditorInfo.IME_ACTION_GO,
            EditorInfo.IME_ACTION_SEARCH,
            EditorInfo.IME_ACTION_NEXT,
            EditorInfo.IME_ACTION_PREVIOUS -> currentImeAction
            else -> currentEditorActionId.takeIf { it != 0 }
                ?: EditorInfo.IME_ACTION_UNSPECIFIED
        }
    }

    private fun clearComposition() {
        if (isSensitiveField()) {
            clearTransientRimeState(recreateSession = false, destroySession = true)
            return
        }

        val state = if (isChineseMode && ensureRimeSession()) {
            rimeEngine.getContext(rimeSessionId)
        } else {
            null
        }
        if (state != null && state.isComposing && state.composition.isNotEmpty()) {
            clearEditorComposition(forceClear = true)
        } else {
            clearEditorComposition()
        }
        if (::rimeEngine.isInitialized && rimeSessionId > 0) {
            rimeSessionId = RimeSessionLifecycle.destroySession(rimeEngine, rimeSessionId)
        }
        clearKeyboardRimeState()
    }

    private fun flushRimeContext() {
        if (isSensitiveField() || rimeSessionId <= 0) {
            clearEditorComposition()
            clearKeyboardRimeState()
            return
        }

        val state = rimeEngine.getContext(rimeSessionId)
        val ic = currentInputConnection

        if (state.isComposing && state.composition.isNotEmpty() && ic != null) {
            setEditorComposingText(state.composition, ic)
        } else {
            clearEditorComposition()
        }

        if (::keyboardView.isInitialized) {
            keyboardView.composition = if (state.isComposing) state.composition else ""
            keyboardView.candidates = state.candidates.map { it.text }
            keyboardView.highlightedCandidateIndex = state.highlightedIndex
            keyboardView.canPageBackward = state.canPageBackward
            keyboardView.canPageForward = state.canPageForward
            keyboardView.invalidate()
        }
    }

    private fun flushRimeCommit(): Boolean {
        if (isSensitiveField() || rimeSessionId <= 0) return false

        val commit = rimeEngine.getCommit(rimeSessionId)
        if (commit != null) {
            commitText(commit)
            return true
        }
        return false
    }

    private fun commitRawCharacter(code: Int) {
        val upperCase = ::keyboardView.isInitialized && keyboardView.isUpperCase
        val text = code.toChar().let {
            if (upperCase) it.uppercaseChar() else it
        }
        commitText(text.toString())

        // Auto lowercase after one uppercase character.
        if (upperCase) {
            keyboardView.isUpperCase = false
            keyboardView.invalidate()
        }
    }

    private fun commitText(text: String) {
        commitText(currentInputConnection ?: return, text)
    }

    private fun commitText(ic: InputConnection, text: String) {
        ic.commitText(text, 1)
        editorCompositionTracker.markCommitted()
    }

    private fun setEditorComposingText(text: CharSequence, ic: InputConnection) {
        editorCompositionTracker.setComposingText(text) { value ->
            ic.setComposingText(value, 1)
        }
    }

    private fun clearEditorComposition(forceClear: Boolean = false) {
        val ic = currentInputConnection
        if (ic == null) {
            editorCompositionTracker.markCleared()
            return
        }

        editorCompositionTracker.clearBeforeFinishIfNeeded(
            forceClear = forceClear,
            setEmptyComposingText = { ic.setComposingText("", 1) },
            finishComposingText = { ic.finishComposingText() }
        )
    }

    private fun finishEditorCompositionAfterCommit() {
        finishEditorComposition()
    }

    private fun finishEditorComposition() {
        val ic = currentInputConnection
        if (ic == null) {
            editorCompositionTracker.markCleared()
            return
        }

        editorCompositionTracker.finishAfterCommit {
            ic.finishComposingText()
        }
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
        optimizeRequestId += 1
        val requestId = optimizeRequestId
        val inputToken = lifecycleGuard.currentToken()
        setStatus(getString(R.string.status_optimizing))

        Thread {
            val result = cloudClient.clean(plan.textToClean)
            handler.post {
                if (requestId != optimizeRequestId || !lifecycleGuard.isCurrent(inputToken)) {
                    return@post
                }
                isOptimizing = false
                if (isSensitiveField()) {
                    setStatus(getString(R.string.status_skipped_sensitive))
                    clearStatusAfterDelay()
                    return@post
                }
                when (result) {
                    is CleanResult.Success -> {
                        val cleaned = result.text
                        val replIc = currentInputConnection
                        if (replIc != null) {
                            if (!TextReplacementPlanner.snapshotMatchesPlan(plan, replIc)) {
                                setStatus(getString(R.string.status_text_changed))
                                clearStatusAfterDelay()
                                return@post
                            }
                            if (plan.isSelectedText) {
                                commitText(replIc, cleaned)
                            } else {
                                replIc.deleteSurroundingText(plan.beforeLength, 0)
                                commitText(replIc, cleaned)
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
        if (isSensitiveField()) {
            setStatus(getString(R.string.status_skipped_sensitive))
            clearStatusAfterDelay()
            return
        }

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
        commitText(ic, entry.before)
        setStatus("undone")
        clearStatusAfterDelay()
    }

    private fun toggleChineseMode() {
        isChineseMode = !isChineseMode
        clearTransientRimeState(recreateSession = false, destroySession = true)
        if (::keyboardView.isInitialized) {
            keyboardView.isChineseMode = isChineseMode
            keyboardView.invalidate()
        }
        setStatus(if (isChineseMode) "中文" else "EN")
        clearStatusAfterDelay()
    }

    private fun openSettings() {
        val intent = android.content.Intent(this, SettingsActivity::class.java).apply {
            addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
    }

    private fun hideKeyboard() {
        clearTransientRimeState(recreateSession = false, destroySession = true)
        requestHideSelf(0)
    }

    private fun switchToNextIme() {
        clearTransientRimeState(recreateSession = false, destroySession = true)
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            if (!switchToNextInputMethod(false)) {
                imm.showInputMethodPicker()
            }
        } else {
            imm.showInputMethodPicker()
        }
    }

    // --- Voice input ---

    private fun startVoiceInput(mode: VoiceSessionMode): Boolean {
        if (voiceSessionMode != VoiceSessionMode.NONE) {
            cancelVoiceSession(finalizePartial = true)
        }

        if (isSensitiveField()) {
            setStatus(getString(R.string.status_skipped_sensitive))
            clearStatusAfterDelay()
            return false
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            setStatus("mic permission needed")
            clearStatusAfterDelay()
            return false
        }

        resolveActiveRimeComposition()
        setStatus("listening…")
        voiceSessionMode = mode
        hasVoiceComposingText = false
        voiceRequestId += 1
        val requestId = voiceRequestId
        val inputToken = lifecycleGuard.currentToken()
        fun isCurrentVoiceRequest(): Boolean {
            return requestId == voiceRequestId &&
                    lifecycleGuard.isCurrent(inputToken) &&
                    voiceSessionMode != VoiceSessionMode.NONE &&
                    !isSensitiveField()
        }

        voiceInputManager.startListening(object : VoiceInputManager.Callback {
            override fun onPartialResult(text: String) {
                if (isCurrentVoiceRequest()) {
                    setVoiceComposingText(text)
                    setStatus("…")
                }
            }

            override fun onFinalResult(text: String) {
                when (VoiceSessionPolicy.finalResultAction(voiceSessionMode, isCurrentVoiceRequest())) {
                    VoiceFinalResultAction.IGNORE -> return
                    VoiceFinalResultAction.FINISH -> {
                        commitVoiceFinalResult(text)
                        finishVoiceSessionAfterFinal()
                    }
                    VoiceFinalResultAction.RESTART -> {
                        commitVoiceFinalResult(text)
                        scheduleVoiceRestartAfterFinal(
                            callback = this,
                            isCurrentVoiceRequest = { isCurrentVoiceRequest() },
                        )
                    }
                }
            }

            override fun onError(error: String) {
                handleVoiceError(error, errorCode = null) { isCurrentVoiceRequest() }
            }

            override fun onError(error: String, errorCode: Int) {
                handleVoiceError(error, errorCode) { isCurrentVoiceRequest() }
            }

            override fun onReady() {
                if (isCurrentVoiceRequest()) {
                    setStatus("speak now")
                }
            }

            override fun onEndOfSpeech() {
                if (isCurrentVoiceRequest()) {
                    setStatus("processing…")
                }
            }

            override fun onStatus(status: String) {
                if (isCurrentVoiceRequest()) {
                    setStatus(status)
                }
            }
        }, restartOnSilence = true)
        return true
    }

    private fun scheduleVoiceRestartAfterFinal(
        callback: VoiceInputManager.Callback,
        isCurrentVoiceRequest: () -> Boolean,
    ) {
        val scheduledRequestId = voiceRequestId
        handler.postDelayed({
            if (scheduledRequestId != voiceRequestId) return@postDelayed

            when (VoiceSessionPolicy.finalResultAction(voiceSessionMode, isCurrentVoiceRequest())) {
                VoiceFinalResultAction.RESTART -> {
                    setStatus("listening…")
                    voiceInputManager.startListening(callback, restartOnSilence = true)
                }
                VoiceFinalResultAction.FINISH -> finishVoiceSessionAfterFinal()
                VoiceFinalResultAction.IGNORE -> Unit
            }
        }, VOICE_FINAL_RESTART_DELAY_MS)
    }

    private fun handleSpaceVoiceHoldReleased(heldAfterStartMs: Long) {
        if (voiceSessionMode != VoiceSessionMode.HOLD) return

        when (SpaceVoiceHoldPolicy.releaseAction(heldAfterStartMs)) {
            SpaceVoiceReleaseAction.LOCK -> {
                voiceSessionMode = VoiceSessionMode.LOCKED
                setStatus("listening…")
            }
            SpaceVoiceReleaseAction.STOP -> {
                voiceSessionMode = VoiceSessionMode.STOPPING
                voiceInputManager.stopListening()
                setStatus("processing…")
            }
        }
    }

    private fun stopVoiceBeforeUserAction() {
        if (voiceSessionMode == VoiceSessionMode.LOCKED ||
            voiceSessionMode == VoiceSessionMode.STOPPING
        ) {
            cancelVoiceSession(finalizePartial = true)
        }
    }

    private fun cancelVoiceSession(finalizePartial: Boolean) {
        if (voiceSessionMode == VoiceSessionMode.NONE &&
            !hasVoiceComposingText &&
            (!::voiceInputManager.isInitialized || !voiceInputManager.isActive())
        ) {
            return
        }

        voiceRequestId += 1
        voiceSessionMode = VoiceSessionMode.NONE
        if (::voiceInputManager.isInitialized) {
            voiceInputManager.cancelListening()
        }
        if (finalizePartial) {
            finishVoiceCompositionIfNeeded()
        } else {
            hasVoiceComposingText = false
        }
        setStatus("")
    }

    private fun cancelVoiceSessionForLifecycle() {
        voiceRequestId += 1
        voiceSessionMode = VoiceSessionMode.NONE
        hasVoiceComposingText = false
        if (::voiceInputManager.isInitialized) {
            voiceInputManager.cancelListening()
        }
    }

    private fun setVoiceComposingText(text: String) {
        if (text.isEmpty()) return
        val ic = currentInputConnection ?: return
        setEditorComposingText(text, ic)
        hasVoiceComposingText = true
    }

    private fun commitVoiceFinalResult(text: String) {
        if (text.isNotEmpty()) {
            commitText(text)
            finishEditorCompositionAfterCommit()
        } else {
            finishVoiceCompositionIfNeeded()
        }
        hasVoiceComposingText = false
    }

    private fun finishVoiceCompositionIfNeeded() {
        if (!hasVoiceComposingText) return
        finishEditorComposition()
        hasVoiceComposingText = false
    }

    private fun finishVoiceSessionAfterFinal() {
        voiceSessionMode = VoiceSessionMode.NONE
        setStatus("")
    }

    private fun handleVoiceError(
        error: String,
        errorCode: Int?,
        isCurrentVoiceRequest: () -> Boolean,
    ) {
        if (!isCurrentVoiceRequest()) return

        if (errorCode != null &&
            VoiceRecognizerFallbackPolicy.isRecoverableSilenceError(errorCode)
        ) {
            finishVoiceCompositionIfNeeded()
            voiceSessionMode = VoiceSessionMode.NONE
            setStatus("")
            return
        }

        finishVoiceCompositionIfNeeded()
        voiceSessionMode = VoiceSessionMode.NONE
        setStatus("voice: $error")
        clearStatusAfterDelay()
    }

    // --- Status helpers ---

    private fun setStatus(text: String) {
        if (lifecycleGuard.isDestroyed()) return

        statusText = text
        if (::keyboardView.isInitialized) {
            keyboardView.statusText = text
            keyboardView.invalidate()
        }
    }

    private fun clearStatusAfterDelay() {
        val inputToken = lifecycleGuard.currentToken()
        handler.postDelayed({
            if (lifecycleGuard.isCurrent(inputToken) &&
                statusText.isNotEmpty() &&
                !isOptimizing &&
                !isSensitiveField()
            ) {
                setStatus("")
            }
        }, 2500)
    }

    override fun onDestroy() {
        lifecycleGuard.markDestroyed()
        optimizeRequestId += 1
        voiceRequestId += 1
        voiceSessionMode = VoiceSessionMode.NONE
        hasVoiceComposingText = false
        handler.removeCallbacksAndMessages(null)
        if (::voiceInputManager.isInitialized) {
            voiceInputManager.destroy()
        }
        if (::rimeEngine.isInitialized) {
            rimeSessionId = RimeSessionLifecycle.destroySession(rimeEngine, rimeSessionId)
            rimeEngine.finalize()
        }
        super.onDestroy()
    }
}
