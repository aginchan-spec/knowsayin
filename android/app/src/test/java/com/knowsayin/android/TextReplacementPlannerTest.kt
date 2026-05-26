package com.knowsayin.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class TextReplacementPlannerTest {

    @Test
    fun `plan returns null for empty text`() {
        assertNull(TextReplacementPlanner.planFromTexts("", ""))
    }

    @Test
    fun `plan uses selected text when available`() {
        val plan = TextReplacementPlanner.planFromTexts("hello world", "some other text")
        assertNotNull(plan)
        assertEquals("hello world", plan!!.textToClean)
        assertEquals(true, plan.isSelectedText)
        assertEquals(11, plan.beforeLength)
    }

    @Test
    fun `plan falls back to before-cursor text`() {
        val plan = TextReplacementPlanner.planFromTexts("", "  hello world  ")
        assertNotNull(plan)
        assertEquals("hello world", plan!!.textToClean)
        assertEquals(false, plan.isSelectedText)
    }

    @Test
    fun `plan trims whitespace from selected text`() {
        val plan = TextReplacementPlanner.planFromTexts("  trimmed  ", "")
        assertNotNull(plan)
        assertEquals("trimmed", plan!!.textToClean)
    }

    @Test
    fun `plan returns null for whitespace-only before-cursor`() {
        assertNull(TextReplacementPlanner.planFromTexts("", "   "))
    }

    @Test
    fun `plan returns null for null inputs with whitespace`() {
        assertNull(TextReplacementPlanner.planFromTexts(null, "   "))
    }

    @Test
    fun `plan handles null selected with valid before-cursor`() {
        val plan = TextReplacementPlanner.planFromTexts(null, "  hello  ")
        assertNotNull(plan)
        assertEquals("hello", plan!!.textToClean)
        assertEquals(false, plan.isSelectedText)
    }

    @Test
    fun `plan ignores whitespace-only selected text`() {
        val plan = TextReplacementPlanner.planFromTexts("   ", "useful text")
        assertNotNull(plan)
        assertEquals("useful text", plan!!.textToClean)
        assertEquals(false, plan.isSelectedText)
    }

    @Test
    fun `plan captures full selected text snapshot for validation`() {
        val snapshot = TextReplacementPlanner.InputSnapshot(
            selectedText = "  clean this  ",
            beforeCursorText = "prefix ",
            afterCursorText = " suffix"
        )

        val plan = TextReplacementPlanner.planFromSnapshot(snapshot)

        assertNotNull(plan)
        assertEquals("clean this", plan!!.textToClean)
        assertEquals(snapshot, plan.capturedSnapshot)
        assertEquals(true, TextReplacementPlanner.snapshotMatchesPlan(plan, snapshot))
    }

    @Test
    fun `snapshot validation rejects selected text changes`() {
        val plan = TextReplacementPlanner.planFromSnapshot(
            TextReplacementPlanner.InputSnapshot(
                selectedText = "clean this",
                beforeCursorText = "prefix ",
                afterCursorText = " suffix"
            )
        )
        assertNotNull(plan)

        val changedSelection = TextReplacementPlanner.InputSnapshot(
            selectedText = "other text",
            beforeCursorText = "prefix ",
            afterCursorText = " suffix"
        )

        assertEquals(false, TextReplacementPlanner.snapshotMatchesPlan(plan!!, changedSelection))
    }

    @Test
    fun `snapshot validation rejects before cursor edits`() {
        val plan = TextReplacementPlanner.planFromSnapshot(
            TextReplacementPlanner.InputSnapshot(
                selectedText = "",
                beforeCursorText = "rough prompt",
                afterCursorText = ""
            )
        )
        assertNotNull(plan)

        val editedBeforeCursor = TextReplacementPlanner.InputSnapshot(
            selectedText = "",
            beforeCursorText = "rough prompt plus typing",
            afterCursorText = ""
        )

        assertEquals(false, TextReplacementPlanner.snapshotMatchesPlan(plan!!, editedBeforeCursor))
    }

    @Test
    fun `snapshot validation rejects cursor moves that change after text`() {
        val plan = TextReplacementPlanner.planFromSnapshot(
            TextReplacementPlanner.InputSnapshot(
                selectedText = "",
                beforeCursorText = "rough prompt",
                afterCursorText = " tail"
            )
        )
        assertNotNull(plan)

        val movedCursor = TextReplacementPlanner.InputSnapshot(
            selectedText = "",
            beforeCursorText = "rough prompt",
            afterCursorText = ""
        )

        assertEquals(false, TextReplacementPlanner.snapshotMatchesPlan(plan!!, movedCursor))
    }
}
