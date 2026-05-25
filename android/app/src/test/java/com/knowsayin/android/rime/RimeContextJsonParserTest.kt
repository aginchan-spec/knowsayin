package com.knowsayin.android.rime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RimeContextJsonParserTest {

    @Test
    fun `parses object candidates`() {
        val state = RimeContextJsonParser.parse(
            """
            {
              "composition": "nihao",
              "compositionCursor": 5,
              "candidates": [
                {"text": "你好", "comment": "ni hao"},
                {"text": "你号", "comment": ""}
              ],
              "highlightedIndex": 1,
              "isComposing": true
            }
            """.trimIndent()
        )

        assertEquals("nihao", state.composition)
        assertEquals(5, state.compositionCursor)
        assertEquals(2, state.candidates.size)
        assertEquals(RimeCandidate("你好", "ni hao"), state.candidates[0])
        assertEquals(RimeCandidate("你号", ""), state.candidates[1])
        assertEquals(1, state.highlightedIndex)
        assertTrue(state.isComposing)
    }

    @Test
    fun `parses string candidates`() {
        val state = RimeContextJsonParser.parse(
            """{"composition":"ba ba","candidates":["爸爸","巴巴"],"isComposing":true}"""
        )

        assertEquals("ba ba", state.composition)
        assertEquals(listOf(RimeCandidate("爸爸"), RimeCandidate("巴巴")), state.candidates)
        assertTrue(state.isComposing)
    }

    @Test
    fun `returns empty state for invalid json`() {
        val state = RimeContextJsonParser.parse("not-json")

        assertEquals("", state.composition)
        assertEquals(emptyList<RimeCandidate>(), state.candidates)
        assertFalse(state.isComposing)
    }

    @Test
    fun `defaults composing from composition and candidates`() {
        val state = RimeContextJsonParser.parse(
            """{"composition":"ni","candidates":[{"text":"你"}]}"""
        )

        assertTrue(state.isComposing)
        assertEquals(2, state.compositionCursor)
    }
}
