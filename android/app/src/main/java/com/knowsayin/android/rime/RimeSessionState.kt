package com.knowsayin.android.rime

data class RimeSessionState(
    val composition: String = "",
    val compositionCursor: Int = 0,
    val candidates: List<RimeCandidate> = emptyList(),
    val highlightedIndex: Int = 0,
    val pageSize: Int = 0,
    val pageNumber: Int = 0,
    val isLastPage: Boolean = true,
    val selectKeys: String = "",
    val commit: String? = null,
    val isComposing: Boolean = false
) {
    val canPageBackward: Boolean
        get() = candidates.isNotEmpty() && pageNumber > 0

    val canPageForward: Boolean
        get() = candidates.isNotEmpty() && !isLastPage
}
