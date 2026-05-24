package com.knowsayin.android.rime

private val PINYIN_DICT = mapOf(
    "nihao" to listOf("你好", "你号", "妮好", "拟好"),
    "shijie" to listOf("世界", "师姐", "时节", "视界"),
    "zhongguo" to listOf("中国", "钟国", "种过"),
    "xiexie" to listOf("谢谢", "写写", "歇歇"),
    "zaoshang" to listOf("早上", "枣上"),
    "haode" to listOf("好的", "好得"),
    "mingtian" to listOf("明天", "名天"),
    "jintian" to listOf("今天", "金天"),
    "zhidao" to listOf("知道", "直道", "指导"),
    "xuexi" to listOf("学习", "血洗"),
    "gongzuo" to listOf("工作", "供桌"),
    "pengyou" to listOf("朋友", "碰友"),
    "dianhua" to listOf("电话", "点画"),
    "kaishi" to listOf("开始", "凯仕"),
    "jieshu" to listOf("结束", "借书"),
    "bangzhu" to listOf("帮助", "绑住"),
    "xihuan" to listOf("喜欢", "洗换"),
    "shenme" to listOf("什么", "神么"),
    "zenme" to listOf("怎么", "怎末"),
    "weixin" to listOf("微信", "维新", "违心"),
)

class StubRimeEngine : RimeEngine {

    private val sessions = mutableMapOf<Long, StubSession>()

    override fun initialize(dataDir: String): Boolean = true

    override fun createSession(): Long {
        val id = System.nanoTime() and 0x7FFFFFFFFFFFFFFFL
        sessions[id] = StubSession()
        return id
    }

    override fun destroySession(sessionId: Long): Boolean {
        sessions.remove(sessionId)
        return true
    }

    override fun processKey(sessionId: Long, keycode: Int, mask: Int): Boolean {
        val session = sessions[sessionId] ?: return false
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
        session.pendingCommit = candidates[index].text
        session.inputBuffer.clear()
        session.currentCandidates = emptyList()
        return true
    }

    override fun finalize() {
        sessions.clear()
    }

    private fun keycodeToChar(keycode: Int): Char? {
        return when (keycode) {
            in android.view.KeyEvent.KEYCODE_A..android.view.KeyEvent.KEYCODE_Z ->
                ('a' + (keycode - android.view.KeyEvent.KEYCODE_A))
            android.view.KeyEvent.KEYCODE_SPACE -> ' '
            android.view.KeyEvent.KEYCODE_APOSTROPHE -> '\''
            else -> null
        }
    }
}

private class StubSession {
    val inputBuffer = StringBuilder()
    var currentCandidates: List<RimeCandidate> = emptyList()
    var pendingCommit: String? = null

    fun updateCandidates() {
        val pinyin = inputBuffer.toString().lowercase()
        currentCandidates = PINYIN_DICT[pinyin]
            ?.map { RimeCandidate(it) }
            ?: emptyList()
    }
}
