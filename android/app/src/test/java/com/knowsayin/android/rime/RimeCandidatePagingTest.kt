package com.knowsayin.android.rime

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RimeCandidatePagingTest {

    @Test
    fun `next page is available only before last page`() {
        val state = RimeSessionState(
            candidates = listOf(RimeCandidate("是")),
            pageNumber = 0,
            isLastPage = false
        )

        assertTrue(RimeCandidatePaging.canPage(state, RimeCandidatePageDirection.NEXT))
        assertFalse(RimeCandidatePaging.canPage(state, RimeCandidatePageDirection.PREVIOUS))
    }

    @Test
    fun `previous page is available after first page`() {
        val state = RimeSessionState(
            candidates = listOf(RimeCandidate("世")),
            pageNumber = 1,
            isLastPage = true
        )

        assertTrue(RimeCandidatePaging.canPage(state, RimeCandidatePageDirection.PREVIOUS))
        assertFalse(RimeCandidatePaging.canPage(state, RimeCandidatePageDirection.NEXT))
    }

    @Test
    fun `paging direction maps to android page keycodes`() {
        assertEquals(KeyEvent.KEYCODE_PAGE_UP, RimeCandidatePageDirection.PREVIOUS.keyCode)
        assertEquals(KeyEvent.KEYCODE_PAGE_DOWN, RimeCandidatePageDirection.NEXT.keyCode)
    }
}
