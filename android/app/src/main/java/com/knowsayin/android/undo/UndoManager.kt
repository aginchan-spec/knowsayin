package com.knowsayin.android.undo

class UndoManager {

    private var undoEntry: UndoEntry? = null

    fun store(before: CharSequence, after: CharSequence) {
        undoEntry = UndoEntry(before = before.toString(), after = after.toString())
    }

    fun pop(): UndoEntry? {
        val entry = undoEntry
        undoEntry = null
        return entry
    }

    fun hasUndo(): Boolean = undoEntry != null

    fun clear() {
        undoEntry = null
    }

    data class UndoEntry(
        val before: String,
        val after: String
    )
}
