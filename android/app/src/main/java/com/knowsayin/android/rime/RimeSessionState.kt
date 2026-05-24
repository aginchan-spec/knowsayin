package com.knowsayin.android.rime

data class RimeSessionState(
    val composition: String = "",
    val compositionCursor: Int = 0,
    val candidates: List<RimeCandidate> = emptyList(),
    val highlightedIndex: Int = 0,
    val commit: String? = null,
    val isComposing: Boolean = false
)
