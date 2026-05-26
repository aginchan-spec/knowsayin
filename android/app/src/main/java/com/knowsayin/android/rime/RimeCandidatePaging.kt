package com.knowsayin.android.rime

import android.view.KeyEvent

enum class RimeCandidatePageDirection(val keyCode: Int) {
    PREVIOUS(KeyEvent.KEYCODE_PAGE_UP),
    NEXT(KeyEvent.KEYCODE_PAGE_DOWN)
}

object RimeCandidatePaging {

    fun canPage(state: RimeSessionState, direction: RimeCandidatePageDirection): Boolean {
        return when (direction) {
            RimeCandidatePageDirection.PREVIOUS -> state.canPageBackward
            RimeCandidatePageDirection.NEXT -> state.canPageForward
        }
    }
}
