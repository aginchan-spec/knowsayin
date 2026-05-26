package com.knowsayin.android

internal class EditorCompositionTracker {
    var hasActiveComposition: Boolean = false
        private set

    fun setComposingText(
        text: CharSequence,
        setComposingText: (CharSequence) -> Boolean
    ) {
        setComposingText(text)
        hasActiveComposition = text.isNotEmpty()
    }

    fun clearBeforeFinishIfNeeded(
        forceClear: Boolean = false,
        setEmptyComposingText: () -> Boolean,
        finishComposingText: () -> Boolean
    ) {
        if (forceClear || hasActiveComposition) {
            setEmptyComposingText()
        }
        finishComposingText()
        hasActiveComposition = false
    }

    fun finishAfterCommit(finishComposingText: () -> Boolean) {
        finishComposingText()
        hasActiveComposition = false
    }

    fun markCommitted() {
        hasActiveComposition = false
    }

    fun markCleared() {
        hasActiveComposition = false
    }

    fun markInputLifecycleChanged() {
        hasActiveComposition = false
    }
}
