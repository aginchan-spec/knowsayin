package com.knowsayin.android

import android.view.inputmethod.InputConnection

object TextReplacementPlanner {

    const val MAX_BEFORE_CURSOR_CHARS = 500
    const val MAX_AFTER_CURSOR_CHARS = 500

    data class InputSnapshot(
        val selectedText: String,
        val beforeCursorText: String,
        val afterCursorText: String
    )

    data class ReplacementPlan(
        val textToClean: String,
        val beforeLength: Int,
        val afterLength: Int,
        val isSelectedText: Boolean,
        val capturedSnapshot: InputSnapshot
    )

    fun planFromTexts(
        selectedText: CharSequence?,
        beforeCursor: CharSequence?,
        maxChars: Int = MAX_BEFORE_CURSOR_CHARS
    ): ReplacementPlan? {
        val snapshot = InputSnapshot(
            selectedText = selectedText.asSnapshotText(),
            beforeCursorText = beforeCursor.asSnapshotText().takeLast(maxChars),
            afterCursorText = ""
        )
        return planFromSnapshot(snapshot)
    }

    fun planFromSnapshot(snapshot: InputSnapshot): ReplacementPlan? {
        val selected = snapshot.selectedText
        if (selected.isNotEmpty() && selected.isNotBlank()) {
            return ReplacementPlan(
                textToClean = selected.trim(),
                beforeLength = selected.length,
                afterLength = 0,
                isSelectedText = true,
                capturedSnapshot = snapshot
            )
        }

        val beforeText = snapshot.beforeCursorText
        if (beforeText.isBlank()) return null

        val trimmed = beforeText.trim()
        return ReplacementPlan(
            textToClean = trimmed,
            beforeLength = beforeText.length,
            afterLength = 0,
            isSelectedText = false,
            capturedSnapshot = snapshot
        )
    }

    fun plan(ic: InputConnection): ReplacementPlan? {
        return planFromSnapshot(snapshot(ic))
    }

    fun snapshotMatchesPlan(plan: ReplacementPlan, currentSnapshot: InputSnapshot): Boolean {
        return currentSnapshot == plan.capturedSnapshot
    }

    fun snapshotMatchesPlan(plan: ReplacementPlan, ic: InputConnection): Boolean {
        return snapshotMatchesPlan(plan, snapshot(ic))
    }

    private fun snapshot(ic: InputConnection): InputSnapshot {
        return InputSnapshot(
            selectedText = ic.getSelectedText(0).asSnapshotText(),
            beforeCursorText = ic.getTextBeforeCursor(MAX_BEFORE_CURSOR_CHARS, 0).asSnapshotText(),
            afterCursorText = ic.getTextAfterCursor(MAX_AFTER_CURSOR_CHARS, 0).asSnapshotText()
        )
    }

    private fun CharSequence?.asSnapshotText(): String {
        return this?.toString() ?: ""
    }
}
