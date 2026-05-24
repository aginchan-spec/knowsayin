package com.knowsayin.android

import android.view.inputmethod.InputConnection

object TextReplacementPlanner {

    const val MAX_BEFORE_CURSOR_CHARS = 500

    data class ReplacementPlan(
        val textToClean: String,
        val beforeLength: Int,
        val afterLength: Int,
        val isSelectedText: Boolean
    )

    fun planFromTexts(
        selectedText: CharSequence?,
        beforeCursor: CharSequence?,
        maxChars: Int = MAX_BEFORE_CURSOR_CHARS
    ): ReplacementPlan? {
        val selected = (selectedText ?: "").toString()
        if (selected.isNotEmpty() && selected.isNotBlank()) {
            return ReplacementPlan(
                textToClean = selected.trim(),
                beforeLength = selected.length,
                afterLength = 0,
                isSelectedText = true
            )
        }

        val beforeText = (beforeCursor ?: "").toString()
        if (beforeText.isBlank()) return null

        val trimmed = beforeText.trim()
        return ReplacementPlan(
            textToClean = trimmed,
            beforeLength = beforeText.length,
            afterLength = 0,
            isSelectedText = false
        )
    }

    fun plan(ic: InputConnection): ReplacementPlan? {
        val selected = ic.getSelectedText(0)
        val plan = planFromTexts(selected, null)
        if (plan != null) return plan

        val before = ic.getTextBeforeCursor(MAX_BEFORE_CURSOR_CHARS, 0)
        return planFromTexts(null, before)
    }
}
