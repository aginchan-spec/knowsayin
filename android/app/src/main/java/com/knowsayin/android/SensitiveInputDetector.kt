package com.knowsayin.android

import android.view.inputmethod.EditorInfo

object SensitiveInputDetector {

    fun isSensitive(inputType: Int): Boolean {
        val inputClass = inputType and EditorInfo.TYPE_MASK_CLASS
        val variation = inputType and EditorInfo.TYPE_MASK_VARIATION

        if (inputClass == EditorInfo.TYPE_CLASS_TEXT) {
            return variation == EditorInfo.TYPE_TEXT_VARIATION_PASSWORD
                    || variation == EditorInfo.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                    || variation == EditorInfo.TYPE_TEXT_VARIATION_WEB_PASSWORD
        }
        if (inputClass == EditorInfo.TYPE_CLASS_NUMBER) {
            return variation == EditorInfo.TYPE_NUMBER_VARIATION_PASSWORD
        }
        return false
    }

    fun isFiltered(inputType: Int): Boolean {
        val inputClass = inputType and EditorInfo.TYPE_MASK_CLASS
        val variation = inputType and EditorInfo.TYPE_MASK_VARIATION
        return inputClass == EditorInfo.TYPE_CLASS_TEXT
                && variation == EditorInfo.TYPE_TEXT_VARIATION_FILTER
    }
}
