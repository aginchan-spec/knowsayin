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
}
