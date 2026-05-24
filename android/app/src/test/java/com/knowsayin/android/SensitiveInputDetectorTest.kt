package com.knowsayin.android

import android.view.inputmethod.EditorInfo
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SensitiveInputDetectorTest {

    @Test
    fun `password variation is sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_PASSWORD
        assertTrue(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `visible password variation is sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        assertTrue(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `web password variation is sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_WEB_PASSWORD
        assertTrue(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `normal text is not sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_NORMAL
        assertFalse(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `email variation is not sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
        assertFalse(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `uri variation is not sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_URI
        assertFalse(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `filter variation is filtered`() {
        val inputType = EditorInfo.TYPE_CLASS_TEXT or EditorInfo.TYPE_TEXT_VARIATION_FILTER
        assertTrue(SensitiveInputDetector.isFiltered(inputType))
    }

    @Test
    fun `number password is sensitive`() {
        val inputType = EditorInfo.TYPE_CLASS_NUMBER or EditorInfo.TYPE_NUMBER_VARIATION_PASSWORD
        assertTrue(SensitiveInputDetector.isSensitive(inputType))
    }

    @Test
    fun `null input type returns not sensitive`() {
        assertFalse(SensitiveInputDetector.isSensitive(0))
        assertFalse(SensitiveInputDetector.isFiltered(0))
    }
}
