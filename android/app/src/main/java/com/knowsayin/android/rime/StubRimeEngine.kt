package com.knowsayin.android.rime

import android.content.Context
import android.content.SharedPreferences
import android.view.KeyEvent
import java.io.InputStream
import java.io.Reader
import java.security.MessageDigest

private const val STUB_DICTIONARY_ASSET_PATH = "rime/pinyin_simp.dict.yaml"
private const val STUB_MAX_CANDIDATES_PER_PINYIN = 64
private const val STUB_PAGE_SIZE = 5
private const val STUB_MAX_LOOKUP_CANDIDATES = 128
private const val STUB_COMPOSE_MIN_QUERY_LENGTH = 2
private const val STUB_COMPOSE_BRANCH_LIMIT = 256
private const val STUB_COMPOSE_RESULT_LIMIT = 16

private const val EXACT_SCORE_BASE = 4_000_000_000_000L
private const val DIRECT_MIXED_SCORE_BASE = 3_500_000_000_000L
private const val PREFIX_SCORE_BASE = 3_000_000_000_000L
private const val COMPOSE_SCORE_BASE = 2_500_000_000_000L
private const val WEIGHT_SCORE_MULTIPLIER = 1_000L
private const val MULTI_SYLLABLE_PREFIX_PENALTY = 150_000_000L
private const val COMPOSE_PART_PENALTY = 5_000_000_000L
private const val COMPOSE_MULTI_SYLLABLE_ENTRY_BONUS = 2_000_000_000L
private const val USER_BOOST_SCORE = 2_000_000_000L

private val BUILT_IN_DICTIONARY = createStubDictionary(
    listOf(
        DictionaryEntry("好", "hao", listOf("hao"), 378_543, 0),
        DictionaryEntry("号", "hao", listOf("hao"), 70_299, 1),
        DictionaryEntry("耗", "hao", listOf("hao"), 5_000, 2),
        DictionaryEntry("豪", "hao", listOf("hao"), 4_000, 3),
        DictionaryEntry("毫", "hao", listOf("hao"), 3_000, 4),
        DictionaryEntry("浩", "hao", listOf("hao"), 2_000, 5),
        DictionaryEntry("郝", "hao", listOf("hao"), 1_000, 6),
        DictionaryEntry("皓", "hao", listOf("hao"), 900, 7),
        DictionaryEntry("哈", "ha", listOf("ha"), 53_642, 8),
        DictionaryEntry("还", "hai", listOf("hai"), 279_642, 9),
        DictionaryEntry("你好", "nihao", listOf("ni", "hao"), 120_000, 10),
        DictionaryEntry("你号", "nihao", listOf("ni", "hao"), 1_000, 11),
        DictionaryEntry("妮好", "nihao", listOf("ni", "hao"), 900, 12),
        DictionaryEntry("拟好", "nihao", listOf("ni", "hao"), 800, 13),
        DictionaryEntry("是", "shi", listOf("shi"), 500_000, 14),
        DictionaryEntry("时", "shi", listOf("shi"), 400_000, 15),
        DictionaryEntry("事", "shi", listOf("shi"), 300_000, 16),
        DictionaryEntry("市", "shi", listOf("shi"), 200_000, 17),
        DictionaryEntry("十", "shi", listOf("shi"), 100_000, 18),
        DictionaryEntry("使", "shi", listOf("shi"), 90_000, 19),
        DictionaryEntry("式", "shi", listOf("shi"), 80_000, 20),
        DictionaryEntry("世", "shi", listOf("shi"), 70_000, 21),
        DictionaryEntry("世界", "shijie", listOf("shi", "jie"), 10_000, 22),
        DictionaryEntry("师姐", "shijie", listOf("shi", "jie"), 1_000, 23),
        DictionaryEntry("时节", "shijie", listOf("shi", "jie"), 900, 24),
        DictionaryEntry("视界", "shijie", listOf("shi", "jie"), 800, 25),
        DictionaryEntry("中国", "zhongguo", listOf("zhong", "guo"), 100_000, 26),
        DictionaryEntry("钟国", "zhongguo", listOf("zhong", "guo"), 1_000, 27),
        DictionaryEntry("种过", "zhongguo", listOf("zhong", "guo"), 900, 28),
        DictionaryEntry("谢谢", "xiexie", listOf("xie", "xie"), 100_000, 29),
        DictionaryEntry("写写", "xiexie", listOf("xie", "xie"), 1_000, 30),
        DictionaryEntry("歇歇", "xiexie", listOf("xie", "xie"), 900, 31),
        DictionaryEntry("早上", "zaoshang", listOf("zao", "shang"), 10_000, 32),
        DictionaryEntry("枣上", "zaoshang", listOf("zao", "shang"), 900, 33),
        DictionaryEntry("好的", "haode", listOf("hao", "de"), 36_136, 34),
        DictionaryEntry("好得", "haode", listOf("hao", "de"), 900, 35),
        DictionaryEntry("明天", "mingtian", listOf("ming", "tian"), 10_000, 36),
        DictionaryEntry("名天", "mingtian", listOf("ming", "tian"), 900, 37),
        DictionaryEntry("今天", "jintian", listOf("jin", "tian"), 10_000, 38),
        DictionaryEntry("金天", "jintian", listOf("jin", "tian"), 900, 39),
        DictionaryEntry("知道", "zhidao", listOf("zhi", "dao"), 10_000, 40),
        DictionaryEntry("直道", "zhidao", listOf("zhi", "dao"), 900, 41),
        DictionaryEntry("指导", "zhidao", listOf("zhi", "dao"), 800, 42),
        DictionaryEntry("学习", "xuexi", listOf("xue", "xi"), 10_000, 43),
        DictionaryEntry("血洗", "xuexi", listOf("xue", "xi"), 900, 44),
        DictionaryEntry("工作", "gongzuo", listOf("gong", "zuo"), 10_000, 45),
        DictionaryEntry("供桌", "gongzuo", listOf("gong", "zuo"), 900, 46),
        DictionaryEntry("朋友", "pengyou", listOf("peng", "you"), 10_000, 47),
        DictionaryEntry("碰友", "pengyou", listOf("peng", "you"), 900, 48),
        DictionaryEntry("电话", "dianhua", listOf("dian", "hua"), 10_000, 49),
        DictionaryEntry("点画", "dianhua", listOf("dian", "hua"), 900, 50),
        DictionaryEntry("开始", "kaishi", listOf("kai", "shi"), 10_000, 51),
        DictionaryEntry("凯仕", "kaishi", listOf("kai", "shi"), 900, 52),
        DictionaryEntry("结束", "jieshu", listOf("jie", "shu"), 10_000, 53),
        DictionaryEntry("借书", "jieshu", listOf("jie", "shu"), 900, 54),
        DictionaryEntry("帮助", "bangzhu", listOf("bang", "zhu"), 10_000, 55),
        DictionaryEntry("绑住", "bangzhu", listOf("bang", "zhu"), 900, 56),
        DictionaryEntry("喜欢", "xihuan", listOf("xi", "huan"), 10_000, 57),
        DictionaryEntry("洗换", "xihuan", listOf("xi", "huan"), 900, 58),
        DictionaryEntry("什么", "shenme", listOf("shen", "me"), 10_000, 59),
        DictionaryEntry("神么", "shenme", listOf("shen", "me"), 900, 60),
        DictionaryEntry("怎么", "zenme", listOf("zen", "me"), 10_000, 61),
        DictionaryEntry("怎末", "zenme", listOf("zen", "me"), 900, 62),
        DictionaryEntry("微信", "weixin", listOf("wei", "xin"), 10_000, 63),
        DictionaryEntry("维新", "weixin", listOf("wei", "xin"), 900, 64),
        DictionaryEntry("违心", "weixin", listOf("wei", "xin"), 800, 65),
        DictionaryEntry("我", "wo", listOf("wo"), 1_192_789, 66),
        DictionaryEntry("我们", "women", listOf("wo", "men"), 322_329, 67),
        DictionaryEntry("为", "wei", listOf("wei"), 210_479, 68),
        DictionaryEntry("问", "wen", listOf("wen"), 49_777, 69),
        DictionaryEntry("无", "wu", listOf("wu"), 32_585, 70),
        DictionaryEntry("我想", "woxiang", listOf("wo", "xiang"), 15_660, 71),
        DictionaryEntry("想", "xiang", listOf("xiang"), 141_790, 72),
        DictionaryEntry("看", "kan", listOf("kan"), 245_039, 73),
        DictionaryEntry("电影", "dianying", listOf("dian", "ying"), 21_545, 74),
        DictionaryEntry("看电影", "kandianying", listOf("kan", "dian", "ying"), 1_693, 75),
        DictionaryEntry("想看", "xiangkan", listOf("xiang", "kan"), 1_150, 76)
    ),
    STUB_MAX_CANDIDATES_PER_PINYIN
)

class StubRimeEngine(
    context: Context? = null,
    private val dictionaryInput: (() -> InputStream)? = null,
    private val maxCandidatesPerPinyin: Int = STUB_MAX_CANDIDATES_PER_PINYIN,
    private val userRanker: StubCandidateRanker = NoOpStubCandidateRanker
) : RimeEngine {

    private val appContext = context?.applicationContext
    private val sessions = mutableMapOf<Long, StubSession>()
    private var dictionary: StubDictionary = BUILT_IN_DICTIONARY

    override fun initialize(dataDir: String): Boolean {
        dictionary = loadDictionary() ?: BUILT_IN_DICTIONARY
        return true
    }

    override fun createSession(): Long {
        val id = System.nanoTime() and 0x7FFFFFFFFFFFFFFFL
        sessions[id] = StubSession(dictionary, userRanker)
        return id
    }

    override fun destroySession(sessionId: Long): Boolean {
        sessions.remove(sessionId)
        return true
    }

    override fun processKey(sessionId: Long, keycode: Int, mask: Int): Boolean {
        val session = sessions[sessionId] ?: return false
        if (keycode == KeyEvent.KEYCODE_PAGE_DOWN) {
            return session.page(forward = true)
        }
        if (keycode == KeyEvent.KEYCODE_PAGE_UP) {
            return session.page(forward = false)
        }
        if (keycode == KeyEvent.KEYCODE_DEL || keycode == '\b'.code) {
            if (session.inputBuffer.isNotEmpty()) {
                session.inputBuffer.deleteAt(session.inputBuffer.length - 1)
                session.updateCandidates()
                return true
            }
            return false
        }
        val ch = keycodeToChar(keycode) ?: return false
        session.inputBuffer.append(ch)
        session.updateCandidates()
        return true
    }

    override fun getContext(sessionId: Long): RimeSessionState {
        val session = sessions[sessionId] ?: return RimeSessionState()
        return RimeSessionState(
            composition = session.inputBuffer.toString(),
            compositionCursor = session.inputBuffer.length,
            candidates = session.currentCandidates,
            highlightedIndex = 0,
            pageSize = STUB_PAGE_SIZE,
            pageNumber = session.pageIndex,
            isLastPage = session.isLastPage,
            selectKeys = "12345",
            isComposing = session.inputBuffer.isNotEmpty()
        )
    }

    override fun getCommit(sessionId: Long): String? {
        val session = sessions[sessionId] ?: return null
        val commit = session.pendingCommit
        session.pendingCommit = null
        return commit
    }

    override fun selectCandidate(sessionId: Long, index: Int): Boolean {
        val session = sessions[sessionId] ?: return false
        val candidates = session.currentCandidates
        if (index < 0 || index >= candidates.size) return false
        val selected = candidates[index].text
        session.userRanker.boost(normalizePinyin(session.inputBuffer.toString()), selected)
        session.pendingCommit = selected
        session.inputBuffer.clear()
        session.allCandidates = emptyList()
        session.currentCandidates = emptyList()
        session.pageIndex = 0
        return true
    }

    override fun finalize() {
        sessions.clear()
    }

    private fun keycodeToChar(keycode: Int): Char? {
        return when (keycode) {
            in 'a'.code..'z'.code -> keycode.toChar()
            in 'A'.code..'Z'.code -> keycode.toChar().lowercaseChar()
            in '0'.code..'9'.code -> keycode.toChar()
            ' '.code, '\''.code, ','.code, '.'.code -> keycode.toChar()
            in KeyEvent.KEYCODE_A..KeyEvent.KEYCODE_Z ->
                ('a' + (keycode - KeyEvent.KEYCODE_A))
            KeyEvent.KEYCODE_SPACE -> ' '
            KeyEvent.KEYCODE_APOSTROPHE -> '\''
            else -> null
        }
    }

    private fun loadDictionary(): StubDictionary? {
        val input = dictionaryInput ?: appContext?.let { context ->
            { context.assets.open(STUB_DICTIONARY_ASSET_PATH) }
        } ?: return null

        return try {
            input().bufferedReader(Charsets.UTF_8).use { reader ->
                parseStubDictionary(reader, maxCandidatesPerPinyin)
                    .takeIf { it.isNotEmpty() }
            }
        } catch (_: Exception) {
            null
        }
    }
}

interface StubCandidateRanker {
    fun boost(query: String, text: String)
    fun boostScore(query: String, text: String): Long
}

object NoOpStubCandidateRanker : StubCandidateRanker {
    override fun boost(query: String, text: String) = Unit
    override fun boostScore(query: String, text: String): Long = 0L
}

class SharedPreferencesStubCandidateRanker(
    private val prefs: SharedPreferences
) : StubCandidateRanker {

    override fun boost(query: String, text: String) {
        if (query.isEmpty() || text.isEmpty()) return
        val key = preferenceKey(query, text)
        val current = prefs.getInt(key, 0)
        prefs.edit().putInt(key, (current + 1).coerceAtMost(MAX_BOOST_COUNT)).apply()
    }

    override fun boostScore(query: String, text: String): Long {
        if (query.isEmpty() || text.isEmpty()) return 0L
        return prefs.getInt(preferenceKey(query, text), 0).toLong() * USER_BOOST_SCORE
    }

    private fun preferenceKey(query: String, text: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$query\u001f$text".toByteArray(Charsets.UTF_8))
        return PREF_PREFIX + hex(digest)
    }

    private fun hex(bytes: ByteArray): String {
        val hexChars = "0123456789abcdef"
        return buildString(bytes.size * 2) {
            for (byte in bytes) {
                val value = byte.toInt() and 0xff
                append(hexChars[value ushr 4])
                append(hexChars[value and 0x0f])
            }
        }
    }

    companion object {
        private const val PREF_PREFIX = "rime_stub_candidate_rank_v1:"
        private const val MAX_BOOST_COUNT = 100
    }
}

private class StubSession(
    private val dictionary: StubDictionary,
    val userRanker: StubCandidateRanker
) {
    val inputBuffer = StringBuilder()
    var allCandidates: List<RimeCandidate> = emptyList()
    var currentCandidates: List<RimeCandidate> = emptyList()
    var pageIndex: Int = 0
    var pendingCommit: String? = null

    val isLastPage: Boolean
        get() = allCandidates.isEmpty() || pageIndex >= lastPageIndex()

    fun updateCandidates() {
        val pinyin = normalizePinyin(inputBuffer.toString())
        allCandidates = dictionary.lookup(pinyin, userRanker)
        pageIndex = 0
        updateCurrentPage()
    }

    fun page(forward: Boolean): Boolean {
        if (allCandidates.isEmpty()) return false
        val nextPage = if (forward) pageIndex + 1 else pageIndex - 1
        if (nextPage < 0 || nextPage > lastPageIndex()) return false
        pageIndex = nextPage
        updateCurrentPage()
        return true
    }

    private fun updateCurrentPage() {
        val start = pageIndex * STUB_PAGE_SIZE
        currentCandidates = allCandidates.drop(start).take(STUB_PAGE_SIZE)
    }

    private fun lastPageIndex(): Int {
        return ((allCandidates.size - 1) / STUB_PAGE_SIZE).coerceAtLeast(0)
    }
}

private data class StubDictionary(
    val byPinyin: Map<String, List<DictionaryEntry>>,
    val entriesByInitial: Map<Char, List<DictionaryEntry>>
) {
    fun isNotEmpty(): Boolean = byPinyin.isNotEmpty()

    fun lookup(query: String, userRanker: StubCandidateRanker): List<RimeCandidate> {
        if (query.isEmpty()) return emptyList()

        val scored = linkedMapOf<String, ScoredCandidate>()
        val initialEntries = entriesByInitial[query.first()].orEmpty()
        val exactEntries = byPinyin[query].orEmpty()
        val shouldUsePrefix = exactEntries.isEmpty() || shouldOfferPrefixAlongsideExact(query)

        exactEntries.forEach { entry ->
            val score = if (shouldRankExactAsPrefix(query)) {
                prefixScore(entry, query)
            } else {
                exactScore(entry)
            }
            scored.offer(entry.toScoredCandidate(query, userRanker, score))
        }

        if (shouldUsePrefix) {
            initialEntries.asSequence()
                .filter { it.normalizedPinyin != query && it.normalizedPinyin.startsWith(query) }
                .forEach { entry ->
                    scored.offer(entry.toScoredCandidate(query, userRanker, prefixScore(entry, query)))
                }
        }

        if (shouldUsePrefix && query.length >= STUB_COMPOSE_MIN_QUERY_LENGTH) {
            initialEntries.asSequence()
                .mapNotNull { entry ->
                    matchEntryAt(query, 0, entry)
                        ?.takeIf { it.end == query.length }
                        ?.let { entry to it }
                }
                .forEach { (entry, match) ->
                    val score = directMixedScore(entry, match)
                    scored.offer(entry.toScoredCandidate(query, userRanker, score))
                }

            composeCandidates(query, userRanker).forEach { candidate ->
                scored.offer(candidate)
            }
        }

        return scored.values
            .sortedWith(scoredCandidateComparator)
            .take(STUB_MAX_LOOKUP_CANDIDATES)
            .map { RimeCandidate(it.text) }
    }

    private fun composeCandidates(
        query: String,
        userRanker: StubCandidateRanker
    ): List<ScoredCandidate> {
        val memo = mutableMapOf<Int, List<ComposePath>>()

        fun dfs(index: Int): List<ComposePath> {
            memo[index]?.let { return it }
            if (index == query.length) {
                return listOf(ComposePath(text = "", score = 0L, weight = 0L, order = Int.MAX_VALUE, parts = 0))
            }

            val matches = entriesByInitial[query[index]].orEmpty()
                .asSequence()
                .mapNotNull { entry ->
                    matchEntryAt(query, index, entry)
                        ?.let { match -> MatchedEntry(entry, match) }
                }
                .sortedWith(matchedEntryComparator)
                .take(STUB_COMPOSE_BRANCH_LIMIT)
                .toList()

            val paths = mutableListOf<ComposePath>()
            for (matched in matches) {
                val tails = dfs(matched.match.end)
                for (tail in tails) {
                    val localScore = matched.entry.weight * WEIGHT_SCORE_MULTIPLIER +
                        matched.match.qualityScore * 50_000_000L -
                        (matched.entry.syllableCount - 1).coerceAtLeast(0) * 10_000L +
                        (matched.entry.syllableCount - 1).coerceAtLeast(0) *
                        COMPOSE_MULTI_SYLLABLE_ENTRY_BONUS
                    val boundaryPenalty = if (tail.parts > 0) COMPOSE_PART_PENALTY else 0L
                    paths += ComposePath(
                        text = matched.entry.text + tail.text,
                        score = localScore + tail.score - boundaryPenalty,
                        weight = matched.entry.weight + tail.weight,
                        order = minOf(matched.entry.order, tail.order),
                        parts = tail.parts + 1
                    )
                }
            }

            val result = paths
                .asSequence()
                .filter { it.text.isNotEmpty() }
                .sortedWith(composePathComparator)
                .distinctBy { it.text }
                .take(STUB_COMPOSE_RESULT_LIMIT)
                .toList()
            memo[index] = result
            return result
        }

        return dfs(0)
            .asSequence()
            .filter { it.parts > 1 }
            .map { path ->
                ScoredCandidate(
                    text = path.text,
                    score = COMPOSE_SCORE_BASE + path.score +
                        userRanker.boostScore(query, path.text),
                    weight = path.weight,
                    order = path.order
                )
            }
            .sortedWith(scoredCandidateComparator)
            .take(STUB_COMPOSE_RESULT_LIMIT)
            .toList()
    }
}

private fun shouldOfferPrefixAlongsideExact(query: String): Boolean {
    return query.length == 2 && query.last() in "aeo"
}

private fun shouldRankExactAsPrefix(query: String): Boolean {
    return query == "ha"
}

private data class DictionaryEntry(
    val text: String,
    val normalizedPinyin: String,
    val syllables: List<String>,
    val weight: Long,
    val order: Int
) {
    val syllableCount: Int = syllables.size
}

private data class ScoredCandidate(
    val text: String,
    val score: Long,
    val weight: Long,
    val order: Int
)

private data class EntryMatch(
    val end: Int,
    val qualityScore: Int
)

private data class MatchState(
    val position: Int,
    val fullCount: Int,
    val partialCount: Int,
    val initialCount: Int,
    val matchedChars: Int
) {
    val qualityScore: Int
        get() = fullCount * 80 + partialCount * 25 - initialCount * 30 + matchedChars
}

private data class MatchedEntry(
    val entry: DictionaryEntry,
    val match: EntryMatch
)

private data class ComposePath(
    val text: String,
    val score: Long,
    val weight: Long,
    val order: Int,
    val parts: Int
)

private val scoredCandidateComparator = compareByDescending<ScoredCandidate> { it.score }
    .thenByDescending { it.weight }
    .thenBy { it.order }
    .thenBy { it.text }

private val matchedEntryComparator = compareByDescending<MatchedEntry> { it.match.end }
    .thenByDescending { it.match.qualityScore }
    .thenByDescending { it.entry.syllableCount }
    .thenByDescending { it.entry.weight }
    .thenBy { it.entry.order }

private val composePathComparator = compareByDescending<ComposePath> { it.score }
    .thenByDescending { it.weight }
    .thenBy { it.parts }
    .thenBy { it.order }

private fun MutableMap<String, ScoredCandidate>.offer(candidate: ScoredCandidate) {
    val current = this[candidate.text]
    if (current == null || scoredCandidateComparator.compare(candidate, current) < 0) {
        this[candidate.text] = candidate
    }
}

private fun DictionaryEntry.toScoredCandidate(
    query: String,
    userRanker: StubCandidateRanker,
    score: Long
): ScoredCandidate {
    return ScoredCandidate(
        text = text,
        score = score + userRanker.boostScore(query, text),
        weight = weight,
        order = order
    )
}

private fun exactScore(entry: DictionaryEntry): Long {
    return EXACT_SCORE_BASE +
        entry.weight * WEIGHT_SCORE_MULTIPLIER -
        entry.order
}

private fun prefixScore(entry: DictionaryEntry, query: String): Long {
    val completionPenalty = (entry.normalizedPinyin.length - query.length).coerceAtLeast(0) * 10L
    val syllablePenalty = (entry.syllableCount - 1).coerceAtLeast(0) * MULTI_SYLLABLE_PREFIX_PENALTY
    return PREFIX_SCORE_BASE +
        entry.weight * WEIGHT_SCORE_MULTIPLIER -
        syllablePenalty -
        completionPenalty -
        entry.order
}

private fun directMixedScore(
    entry: DictionaryEntry,
    match: EntryMatch
): Long {
    return DIRECT_MIXED_SCORE_BASE +
        entry.weight * WEIGHT_SCORE_MULTIPLIER +
        match.qualityScore * 10_000L -
        entry.order
}

private fun matchEntryAt(query: String, start: Int, entry: DictionaryEntry): EntryMatch? {
    var states = listOf(MatchState(start, fullCount = 0, partialCount = 0, initialCount = 0, matchedChars = 0))
    for (syllable in entry.syllables) {
        val nextStates = mutableListOf<MatchState>()
        for (state in states) {
            val maxLength = minOf(syllable.length, query.length - state.position)
            for (length in maxLength downTo 1) {
                if (!query.regionMatches(state.position, syllable, 0, length, ignoreCase = false)) {
                    continue
                }
                val full = if (length == syllable.length) 1 else 0
                val initial = if (length == 1 && length < syllable.length) 1 else 0
                val partial = if (length > 1 && length < syllable.length) 1 else 0
                nextStates += MatchState(
                    position = state.position + length,
                    fullCount = state.fullCount + full,
                    partialCount = state.partialCount + partial,
                    initialCount = state.initialCount + initial,
                    matchedChars = state.matchedChars + length
                )
            }
        }
        if (nextStates.isEmpty()) return null
        states = nextStates
            .sortedWith(
                compareByDescending<MatchState> { it.position }
                    .thenByDescending { it.qualityScore }
            )
            .distinctBy { it.position to it.qualityScore }
            .take(8)
    }

    val best = states.maxWithOrNull(
        compareBy<MatchState> { it.position }
            .thenBy { it.qualityScore }
    ) ?: return null
    return EntryMatch(end = best.position, qualityScore = best.qualityScore)
}

private fun parseStubDictionary(
    reader: Reader,
    maxCandidatesPerPinyin: Int
): StubDictionary {
    val cappedMax = maxCandidatesPerPinyin.coerceAtLeast(1)
    val buckets = linkedMapOf<String, MutableList<DictionaryEntry>>()
    var order = 0

    reader.forEachLine { rawLine ->
        val line = rawLine.trim()
        if (line.isEmpty() || line.startsWith("#") || line == "---" || line == "...") {
            return@forEachLine
        }

        val columns = rawLine.split('\t')
        if (columns.size < 2) return@forEachLine

        val text = columns[0].trim()
        val syllables = parsePinyinSyllables(columns[1])
        val pinyin = syllables.joinToString("")
        if (text.isEmpty() || pinyin.isEmpty() || syllables.isEmpty()) return@forEachLine

        val weight = columns.getOrNull(2)?.trim()?.toLongOrNull() ?: 0L
        buckets.getOrPut(pinyin) { mutableListOf() }
            .add(DictionaryEntry(text, pinyin, syllables, weight, order))
        order += 1
    }

    return createStubDictionary(buckets.values.flatten(), cappedMax)
}

private fun createStubDictionary(
    entries: List<DictionaryEntry>,
    maxCandidatesPerPinyin: Int
): StubDictionary {
    val cappedMax = maxCandidatesPerPinyin.coerceAtLeast(1)
    val byPinyin = entries
        .groupBy { it.normalizedPinyin }
        .mapValues { (_, candidates) ->
            val seen = linkedSetOf<String>()
            candidates.asSequence()
                .sortedWith(
                    compareByDescending<DictionaryEntry> { it.weight }
                        .thenBy { it.order }
                )
                .filter { seen.add(it.text) }
                .take(cappedMax)
                .toList()
        }
        .filterValues { it.isNotEmpty() }

    val byInitial = byPinyin.values
        .flatten()
        .groupBy { it.normalizedPinyin.first() }
        .mapValues { (_, candidates) ->
            candidates.sortedWith(
                compareByDescending<DictionaryEntry> { it.weight }
                    .thenBy { it.order }
            )
        }

    return StubDictionary(byPinyin = byPinyin, entriesByInitial = byInitial)
}

internal fun parsePinyinDictionary(
    reader: Reader,
    maxCandidatesPerPinyin: Int = STUB_MAX_CANDIDATES_PER_PINYIN
): Map<String, List<String>> {
    return parseStubDictionary(reader, maxCandidatesPerPinyin)
        .byPinyin
        .mapValues { (_, candidates) -> candidates.map { it.text } }
}

internal fun normalizePinyin(pinyin: String): String {
    return buildString(pinyin.length) {
        for (char in pinyin.lowercase()) {
            if (char != ' ' && char != '\'') {
                append(char)
            }
        }
    }
}

internal fun parsePinyinSyllables(pinyin: String): List<String> {
    return pinyin.trim()
        .lowercase()
        .split(Regex("[\\s']+"))
        .map { normalizePinyin(it) }
        .filter { it.isNotEmpty() }
}
