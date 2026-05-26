package com.knowsayin.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EditorCompositionTrackerTest {

    @Test
    fun `tracks non empty composing text as active`() {
        val tracker = EditorCompositionTracker()
        val calls = mutableListOf<String>()

        tracker.setComposingText("hao") { text ->
            calls += "set:$text"
            true
        }

        assertTrue(tracker.hasActiveComposition)
        assertEquals(listOf("set:hao"), calls)
    }

    @Test
    fun `clears active composing text before finishing`() {
        val tracker = EditorCompositionTracker()
        val calls = mutableListOf<String>()
        tracker.setComposingText("h") { true }

        tracker.clearBeforeFinishIfNeeded(
            setEmptyComposingText = {
                calls += "set:"
                true
            },
            finishComposingText = {
                calls += "finish"
                true
            }
        )

        assertFalse(tracker.hasActiveComposition)
        assertEquals(listOf("set:", "finish"), calls)
    }

    @Test
    fun `does not set empty composing text when no composition is active`() {
        val tracker = EditorCompositionTracker()
        val calls = mutableListOf<String>()

        tracker.clearBeforeFinishIfNeeded(
            setEmptyComposingText = {
                calls += "set:"
                true
            },
            finishComposingText = {
                calls += "finish"
                true
            }
        )

        assertFalse(tracker.hasActiveComposition)
        assertEquals(listOf("finish"), calls)
    }

    @Test
    fun `commit and input lifecycle clear active tracking`() {
        val tracker = EditorCompositionTracker()

        tracker.setComposingText("ni") { true }
        tracker.markCommitted()
        assertFalse(tracker.hasActiveComposition)

        tracker.setComposingText("wo") { true }
        tracker.markInputLifecycleChanged()
        assertFalse(tracker.hasActiveComposition)
    }

    @Test
    fun `force clear sets empty composing text even without tracked active state`() {
        val tracker = EditorCompositionTracker()
        val calls = mutableListOf<String>()

        tracker.clearBeforeFinishIfNeeded(
            forceClear = true,
            setEmptyComposingText = {
                calls += "set:"
                true
            },
            finishComposingText = {
                calls += "finish"
                true
            }
        )

        assertFalse(tracker.hasActiveComposition)
        assertEquals(listOf("set:", "finish"), calls)
    }
}
