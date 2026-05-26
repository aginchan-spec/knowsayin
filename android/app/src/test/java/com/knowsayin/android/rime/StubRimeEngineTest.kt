package com.knowsayin.android.rime

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.IOException

class StubRimeEngineTest {

    @Test
    fun `pages candidates with page up and page down`() {
        val engine = StubRimeEngine()
        assertTrue(engine.initialize("/tmp/rime"))
        val sessionId = engine.createSession()

        "shi".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val firstPage = engine.getContext(sessionId)
        assertEquals(0, firstPage.pageNumber)
        assertEquals(5, firstPage.pageSize)
        assertEquals(listOf("是", "时", "事", "市", "十"), firstPage.candidates.map { it.text })
        assertFalse(firstPage.canPageBackward)
        assertTrue(firstPage.canPageForward)

        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_PAGE_DOWN, 0))
        val secondPage = engine.getContext(sessionId)
        assertEquals(1, secondPage.pageNumber)
        assertEquals(listOf("使", "式", "世"), secondPage.candidates.map { it.text })
        assertTrue(secondPage.canPageBackward)
        assertFalse(secondPage.canPageForward)

        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_PAGE_UP, 0))
        assertEquals(0, engine.getContext(sessionId).pageNumber)
    }

    @Test
    fun `selects candidates from current page`() {
        val engine = StubRimeEngine()
        engine.initialize("/tmp/rime")
        val sessionId = engine.createSession()
        "shi".forEach { char -> engine.processKey(sessionId, char.code, 0) }

        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_PAGE_DOWN, 0))
        assertTrue(engine.selectCandidate(sessionId, 0))

        assertEquals("使", engine.getCommit(sessionId))
        val state = engine.getContext(sessionId)
        assertFalse(state.isComposing)
        assertEquals(emptyList<RimeCandidate>(), state.candidates)
        assertFalse(engine.processKey(sessionId, KeyEvent.KEYCODE_PAGE_DOWN, 0))
    }

    @Test
    fun `offers basic hao candidates`() {
        val engine = StubRimeEngine()
        engine.initialize("/tmp/rime")
        val sessionId = engine.createSession()

        "hao".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val state = engine.getContext(sessionId)
        assertEquals("hao", state.composition)
        assertEquals(listOf("好", "号", "耗", "豪", "毫"), state.candidates.map { it.text })
        assertTrue(state.canPageForward)
    }

    @Test
    fun `loads single syllable candidates from fixture dictionary source`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        assertTrue(engine.initialize("/tmp/rime"))

        assertCandidatePrefix(engine, "ni", listOf("你", "尼", "呢"))
        assertCandidatePrefix(engine, "wo", listOf("我", "窝"))
        assertCandidatePrefix(engine, "de", listOf("的", "得"))
        assertCandidatePrefix(engine, "hao", listOf("好", "号"))
    }

    @Test
    fun `offers weighted candidates for single letter prefix`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        assertTrue(engine.initialize("/tmp/rime"))
        val sessionId = engine.createSession()

        assertTrue(engine.processKey(sessionId, 'w'.code, 0))

        val candidates = engine.getContext(sessionId).candidates.map { it.text }
        assertEquals("我", candidates.first())
        assertTrue(candidates.contains("为"))
        assertTrue(candidates.indexOf("我") < candidates.indexOf("我们"))
    }

    @Test
    fun `offers likely completions for partial syllable prefix`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        assertTrue(engine.initialize("/tmp/rime"))
        val sessionId = engine.createSession()

        "ha".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val candidates = engine.getContext(sessionId).candidates.map { it.text }
        assertTrue(candidates.contains("好"))
        assertTrue(candidates.contains("号"))
    }

    @Test
    fun `composes mixed initials full and partial pinyin into phrase candidate`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        assertTrue(engine.initialize("/tmp/rime"))
        val sessionId = engine.createSession()

        "wxkandiany".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val state = engine.getContext(sessionId)
        assertEquals("wxkandiany", state.composition)
        assertEquals("我想看电影", state.candidates.first().text)
    }

    @Test
    fun `asset dictionary supports requested prefix and mixed pinyin flows`() {
        val engine = StubRimeEngine(dictionaryInput = { assetDictionary().inputStream() })
        assertTrue(engine.initialize("/tmp/rime"))

        assertCandidatePrefix(engine, "w", listOf("我"))

        val haSessionId = engine.createSession()
        "ha".forEach { char ->
            assertTrue(engine.processKey(haSessionId, char.code, 0))
        }
        val haCandidates = engine.getContext(haSessionId).candidates.map { it.text }
        assertTrue(haCandidates.contains("好"))
        assertTrue(haCandidates.contains("号"))

        val phraseSessionId = engine.createSession()
        "wxkandiany".forEach { char ->
            assertTrue(engine.processKey(phraseSessionId, char.code, 0))
        }
        assertEquals("我想看电影", engine.getContext(phraseSessionId).candidates.first().text)
    }

    @Test
    fun `normalizes spaced and apostrophe dictionary pinyin`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        engine.initialize("/tmp/rime")
        val sessionId = engine.createSession()

        "nihao".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val state = engine.getContext(sessionId)
        assertEquals("nihao", state.composition)
        assertEquals(listOf("你好", "拟好", "妮好"), state.candidates.map { it.text })
    }

    @Test
    fun `ranks loaded candidates by weight and caps stored candidates`() {
        val engine = StubRimeEngine(
            dictionaryInput = { fixtureDictionary().byteInputStream() },
            maxCandidatesPerPinyin = 2
        )
        engine.initialize("/tmp/rime")
        val sessionId = engine.createSession()

        "ni".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val state = engine.getContext(sessionId)
        assertEquals(listOf("你", "尼"), state.candidates.map { it.text })
        assertFalse(state.canPageForward)
    }

    @Test
    fun `boosts selected fallback candidates on later queries`() {
        val ranker = InMemoryStubCandidateRanker()
        val engine = StubRimeEngine(
            dictionaryInput = { fixtureDictionary().byteInputStream() },
            userRanker = ranker
        )
        assertTrue(engine.initialize("/tmp/rime"))

        val firstSessionId = engine.createSession()
        "wo".forEach { char ->
            assertTrue(engine.processKey(firstSessionId, char.code, 0))
        }
        assertEquals(listOf("我", "窝"), engine.getContext(firstSessionId).candidates.map { it.text }.take(2))
        assertTrue(engine.selectCandidate(firstSessionId, 1))
        assertEquals("窝", engine.getCommit(firstSessionId))

        val secondSessionId = engine.createSession()
        "wo".forEach { char ->
            assertTrue(engine.processKey(secondSessionId, char.code, 0))
        }

        assertEquals("窝", engine.getContext(secondSessionId).candidates.first().text)
    }

    @Test
    fun `uses built in candidates when dictionary source fails`() {
        val engine = StubRimeEngine(dictionaryInput = { throw IOException("missing fixture") })
        assertTrue(engine.initialize("/tmp/rime"))

        assertCandidatePrefix(engine, "hao", listOf("好", "号", "耗", "豪", "毫"))
    }

    @Test
    fun `repeated backspace clears composition to empty state`() {
        val engine = StubRimeEngine(dictionaryInput = { fixtureDictionary().byteInputStream() })
        assertTrue(engine.initialize("/tmp/rime"))
        val sessionId = engine.createSession()

        "hao".forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_DEL, 0))
        assertEquals("ha", engine.getContext(sessionId).composition)
        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_DEL, 0))
        assertEquals("h", engine.getContext(sessionId).composition)
        assertTrue(engine.processKey(sessionId, KeyEvent.KEYCODE_DEL, 0))

        val emptyState = engine.getContext(sessionId)
        assertFalse(emptyState.isComposing)
        assertEquals("", emptyState.composition)
        assertEquals(emptyList<RimeCandidate>(), emptyState.candidates)
        assertNull(engine.getCommit(sessionId))
        assertFalse(engine.processKey(sessionId, KeyEvent.KEYCODE_DEL, 0))
    }

    private fun assertCandidatePrefix(
        engine: StubRimeEngine,
        pinyin: String,
        expectedCandidates: List<String>
    ) {
        val sessionId = engine.createSession()
        pinyin.forEach { char ->
            assertTrue(engine.processKey(sessionId, char.code, 0))
        }

        val state = engine.getContext(sessionId)
        assertEquals(pinyin, state.composition)
        assertEquals(expectedCandidates, state.candidates.map { it.text }.take(expectedCandidates.size))
    }

    private fun fixtureDictionary(): String = """
        # Rime dictionary
        # encoding: utf-8
        ---
        name: fixture
        version: "1"
        sort: by_weight
        ...
        你	ni	900
        尼	ni	100
        呢	ni	50
        我	wo	800
        窝	wo	90
        我们	wo men	700
        为	wei	600
        问	wen	200
        的	de	1000
        得	de	500
        好	hao	700
        号	hao	300
        哈	ha	650
        还	hai	600
        还是	hai shi	500
        哈哈	ha ha	400
        你好	ni hao	1200
        妮好	ni hao	20
        拟好	ni'hao	900
        想	xiang	700
        看	kan	650
        电影	dian ying	600
        我想	wo xiang	500
        看电影	kan dian ying	400
        想看	xiang kan	100
    """.trimIndent()

    private fun assetDictionary(): File = File("src/main/assets/rime/pinyin_simp.dict.yaml")

    private class InMemoryStubCandidateRanker : StubCandidateRanker {
        private val counts = mutableMapOf<Pair<String, String>, Long>()

        override fun boost(query: String, text: String) {
            counts[query to text] = (counts[query to text] ?: 0L) + 1L
        }

        override fun boostScore(query: String, text: String): Long {
            return (counts[query to text] ?: 0L) * 2_000_000_000L
        }
    }
}
