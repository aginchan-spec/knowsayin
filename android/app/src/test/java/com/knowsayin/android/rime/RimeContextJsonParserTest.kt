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
              "pageSize": 5,
              "pageNumber": 1,
              "isLastPage": false,
              "selectKeys": "12345",
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
        assertEquals(5, state.pageSize)
        assertEquals(1, state.pageNumber)
        assertFalse(state.isLastPage)
        assertEquals("12345", state.selectKeys)
        assertTrue(state.canPageBackward)
        assertTrue(state.canPageForward)
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
        assertEquals(1, state.pageSize)
        assertEquals(0, state.pageNumber)
        assertTrue(state.isLastPage)
        assertFalse(state.canPageBackward)
        assertFalse(state.canPageForward)
    }

    @Test
    fun `accepts pageNo alias from native style menu metadata`() {
        val state = RimeContextJsonParser.parse(
            """{"composition":"shi","pageNo":2,"isLastPage":true,"candidates":["世"]}"""
        )

        assertEquals(2, state.pageNumber)
        assertTrue(state.canPageBackward)
        assertFalse(state.canPageForward)
    }
}
