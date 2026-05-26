package com.knowsayin.android.keyboard

import org.junit.Assert.assertEquals
import org.junit.Test

class CandidateStripItemsTest {

    @Test
    fun `keeps five short candidates on normal phone width`() {
        val displayed = candidateStripItems(
            candidates = listOf("一", "二", "三", "四", "五", "六", "七"),
            composition = "yi",
            availableWidthDp = 360f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(0, 1, 2, 3, 4), displayed.map { it.originalIndex })
        assertEquals(listOf("一", "二", "三", "四", "五"), displayed.map { it.text })
        assertEquals(listOf(52f, 52f, 52f, 52f, 52f), displayed.map { it.widthDp })
    }

    @Test
    fun `shows long first phrase fully when practical`() {
        val displayed = candidateStripItems(
            candidates = listOf("我想看电影", "我", "想", "看", "的"),
            composition = "wxkandiany",
            availableWidthDp = 316f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(0, 1, 2, 3), displayed.map { it.originalIndex })
        assertEquals(listOf("我想看电影", "我", "想", "看"), displayed.map { it.text })
        assertEquals(listOf(126f, 52f, 52f, 52f), displayed.map { it.widthDp })
    }

    @Test
    fun `stops before following candidate that cannot fit fully`() {
        val displayed = candidateStripItems(
            candidates = listOf("我想看电影", "特别特别长", "我", "想"),
            composition = "wxkandiany",
            availableWidthDp = 210f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(0), displayed.map { it.originalIndex })
        assertEquals(listOf("我想看电影"), displayed.map { it.text })
        assertEquals(listOf(126f), displayed.map { it.widthDp })
    }

    @Test
    fun `uses responsive limit on narrow available width`() {
        val displayed = candidateStripItems(
            candidates = listOf("你好", "您好", "你号", "拟好", "倪好"),
            composition = "nihao",
            availableWidthDp = 190f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(0, 1, 2), displayed.map { it.originalIndex })
        assertEquals(listOf("你好", "您好", "你号"), displayed.map { it.text })
        assertEquals(listOf(60f, 60f, 60f), displayed.map { it.widthDp })
    }

    @Test
    fun `clips to only the first candidate when the first phrase cannot fit`() {
        val displayed = candidateStripItems(
            candidates = listOf("特别特别长的候选短语", "短", "词"),
            composition = "chang",
            availableWidthDp = 90f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(0), displayed.map { it.originalIndex })
        assertEquals(listOf("特别特别长的候选短语"), displayed.map { it.text })
        assertEquals(listOf(90f), displayed.map { it.widthDp })
    }

    @Test
    fun `falls back to composition when no candidates exist`() {
        val displayed = candidateStripItems(
            candidates = emptyList(),
            composition = "hao",
            availableWidthDp = 40f,
            textWidthDp = ::textWidthDp
        )

        assertEquals(listOf(CandidateStripItem(0, "hao", 40f)), displayed)
    }

    private fun textWidthDp(text: String): Float {
        return text.sumOf { char ->
            if (char.code <= 0x7F) 11.0 else 22.0
        }.toFloat()
    }
}
