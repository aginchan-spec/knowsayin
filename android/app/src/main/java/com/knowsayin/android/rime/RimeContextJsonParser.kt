package com.knowsayin.android.rime

import org.json.JSONArray
import org.json.JSONObject

object RimeContextJsonParser {

    fun parse(json: String): RimeSessionState {
        if (json.isBlank()) return RimeSessionState()

        return try {
            val root = JSONObject(json)
            val composition = root.optString("composition", "")
            val candidates = parseCandidates(root.optJSONArray("candidates"))
            RimeSessionState(
                composition = composition,
                compositionCursor = root.optInt("compositionCursor", composition.length),
                candidates = candidates,
                highlightedIndex = root.optInt("highlightedIndex", 0),
                isComposing = root.optBoolean(
                    "isComposing",
                    composition.isNotEmpty() || candidates.isNotEmpty()
                )
            )
        } catch (_: Exception) {
            RimeSessionState()
        }
    }

    private fun parseCandidates(array: JSONArray?): List<RimeCandidate> {
        if (array == null) return emptyList()

        val result = mutableListOf<RimeCandidate>()
        for (i in 0 until array.length()) {
            when (val item = array.opt(i)) {
                is JSONObject -> {
                    val text = item.optString("text", "")
                    if (text.isNotEmpty()) {
                        result += RimeCandidate(
                            text = text,
                            comment = item.optString("comment", "")
                        )
                    }
                }
                is String -> {
                    if (item.isNotEmpty()) {
                        result += RimeCandidate(text = item)
                    }
                }
            }
        }
        return result
    }
}
