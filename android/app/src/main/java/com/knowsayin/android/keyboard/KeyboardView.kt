package com.knowsayin.android.keyboard

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.view.MotionEvent
import android.view.View
import java.util.Locale

class KeyboardView(context: Context) : View(context) {

    interface OnKeyboardActionListener {
        fun onKey(key: Key)
        fun onCandidateSelected(index: Int)
        fun onToolbarAction(action: ToolbarAction)
    }

    enum class ToolbarAction {
        OPTIMIZE, MICROPHONE, UNDO, TOGGLE_CN_EN, SETTINGS, SWITCH_IME
    }

    enum class KeyType {
        CHARACTER, SPACE, BACKSPACE, ENTER, SHIFT, SYMBOL, COMMA, PERIOD, CANDIDATE
    }

    data class Key(
        val type: KeyType,
        val label: String,
        val subLabel: String? = null,
        val code: Int = 0
    )

    var listener: OnKeyboardActionListener? = null
    var isUpperCase: Boolean = false
    var isChineseMode: Boolean = true

    var candidates: List<String> = emptyList()
    var composition: String = ""
    var statusText: String = ""

    private val keyRects = mutableMapOf<Int, RectF>()
    private val candidateRects = mutableListOf<Rect>()
    private val toolbarActions = mutableMapOf<Rect, ToolbarAction>()

    private val keyPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val keyTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.DEFAULT
    }
    private val candidatePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
    }
    private val compositionPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.LEFT
    }
    private val statusPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
    }
    private val toolbarPaint = Paint(Paint.ANTI_ALIAS_FLAG)

    companion object {
        private const val TOOLBAR_HEIGHT_DP = 44f
        private const val CANDIDATE_HEIGHT_DP = 36f
        private const val KEY_GAP_DP = 4f
        private const val KEY_RADIUS_DP = 5f
        private const val STATUS_BAR_HEIGHT_DP = 20f
    }

    private val density: Float get() = resources.displayMetrics.density

    private val toolbarHeight: Int get() = (TOOLBAR_HEIGHT_DP * density).toInt()
    private val candidateHeight: Int get() = (CANDIDATE_HEIGHT_DP * density).toInt()
    private val keyGap: Int get() = (KEY_GAP_DP * density).toInt()
    private val keyRadius: Float get() = KEY_RADIUS_DP * density
    private val statusBarHeight: Int get() = (STATUS_BAR_HEIGHT_DP * density).toInt()

    private val qwertyRows = listOf(
        listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
        listOf("a", "s", "d", "f", "g", "h", "j", "k", "l"),
        listOf("z", "x", "c", "v", "b", "n", "m")
    )

    private val toolbarActionsOrder = listOf(
        ToolbarAction.OPTIMIZE to "\u4f18\u5316",   // 优化
        ToolbarAction.MICROPHONE to "\u9ea6\u514b\u98ce", // 麦克风
        ToolbarAction.UNDO to "Undo",
        ToolbarAction.TOGGLE_CN_EN to "\u4e2d/EN",
        ToolbarAction.SWITCH_IME to "\u2386" // ⎆
    )

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat()
        var y = 0f

        // Status bar
        drawStatusBar(canvas, 0f, y, w, statusBarHeight.toFloat())
        y += statusBarHeight

        // Toolbar
        drawToolbar(canvas, 0f, y, w, toolbarHeight.toFloat())
        y += toolbarHeight

        // Candidate strip
        drawCandidates(canvas, 0f, y, w, candidateHeight.toFloat())
        y += candidateHeight

        // Keyboard area
        drawKeyboard(canvas, 0f, y, w, height - y)
    }

    private fun drawStatusBar(canvas: Canvas, x: Float, y: Float, w: Float, h: Float) {
        val bg = Paint().apply { color = Color.parseColor("#E8EAED") }
        canvas.drawRect(x, y, x + w, y + h, bg)
        compositionPaint.textSize = 12f * density
        compositionPaint.color = Color.BLACK
        canvas.drawText(composition, x + 8f * density, y + h / 2 + 4f * density, compositionPaint)
        if (statusText.isNotEmpty()) {
            statusPaint.textSize = 10f * density
            statusPaint.color = Color.parseColor("#5F6368")
            canvas.drawText(statusText, x + w / 2, y + h / 2 + 4f * density, statusPaint)
        }
    }

    private fun drawToolbar(canvas: Canvas, x: Float, y: Float, w: Float, h: Float) {
        toolbarActions.clear()
        val bg = Paint().apply { color = Color.parseColor("#F1F3F4") }
        canvas.drawRect(x, y, x + w, y + h, bg)

        val actionWidth = w / toolbarActionsOrder.size
        toolbarPaint.textSize = 11f * density
        toolbarPaint.color = Color.parseColor("#1a73e8")
        toolbarPaint.textAlign = Paint.Align.CENTER

        for ((i, pair) in toolbarActionsOrder.withIndex()) {
            val ax = x + i * actionWidth
            val rect = Rect(ax.toInt(), y.toInt(), (ax + actionWidth).toInt(), (y + h).toInt())
            toolbarActions[rect] = pair.first
            canvas.drawText(pair.second, ax + actionWidth / 2, y + h / 2 + 4f * density, toolbarPaint)
        }
    }

    private fun drawCandidates(canvas: Canvas, x: Float, y: Float, w: Float, h: Float) {
        candidateRects.clear()
        val bg = Paint().apply { color = Color.WHITE }
        canvas.drawRect(x, y, x + w, y + h, bg)

        if (candidates.isEmpty()) return

        val candidateWidth = w / candidates.size.coerceAtLeast(1)
        candidatePaint.textSize = 14f * density
        candidatePaint.color = Color.BLACK

        for ((i, cand) in candidates.withIndex()) {
            val cx = x + i * candidateWidth
            val rect = Rect(cx.toInt(), y.toInt(), (cx + candidateWidth).toInt(), (y + h).toInt())
            candidateRects.add(rect)

            // Highlight first candidate
            if (i == 0) {
                val hlBg = Paint().apply { color = Color.parseColor("#E8F0FE") }
                val hlRect = RectF(cx + 2f * density, y + 2f * density,
                    cx + candidateWidth - 2f * density, y + h - 2f * density)
                canvas.drawRoundRect(hlRect, keyRadius, keyRadius, hlBg)
            }
            canvas.drawText(cand, cx + candidateWidth / 2, y + h / 2 + 5f * density, candidatePaint)

            // Divider
            if (i < candidates.size - 1) {
                val divPaint = Paint().apply { color = Color.parseColor("#DADCE0") }
                canvas.drawLine(cx + candidateWidth, y + 8f * density,
                    cx + candidateWidth, y + h - 8f * density, divPaint)
            }
        }
    }

    private fun drawKeyboard(canvas: Canvas, x: Float, y: Float, w: Float, h: Float) {
        keyRects.clear()
        val bg = Paint().apply { color = Color.parseColor("#DADCE0") }
        canvas.drawRect(x, y, x + w, y + h, bg)

        val numRows = 5
        val rowHeight = (h - keyGap * (numRows + 1)) / numRows
        var cy = y + keyGap

        // Row 1: QWERTY
        drawKeyRow(canvas, x, cy, w, rowHeight, qwertyRows[0].map { letter(it) })
        cy += rowHeight + keyGap

        // Row 2: ASDF
        val row2Start = keyGap + (w - keyGap) * 0.05f // slight indent
        drawKeyRow(canvas, x + row2Start.toFloat(), cy, w - row2Start * 2, rowHeight,
            qwertyRows[1].map { letter(it) })
        cy += rowHeight + keyGap

        // Row 3: Shift + ZXCVBNM + Backspace
        drawKeyRowWithSpecials(canvas, x, cy, w, rowHeight,
            listOf(specialKey("Shift", KeyType.SHIFT)) +
                    qwertyRows[2].map { letter(it) } +
                    listOf(specialKey("\u232B", KeyType.BACKSPACE)))
        cy += rowHeight + keyGap

        // Row 4: Symbol + Comma + Space + Period + Enter
        val row4Keys = listOf(
            specialKey("?123", KeyType.SYMBOL),
            specialKey(",", KeyType.COMMA),
            Key(KeyType.SPACE, "space", null, ' '.code),
            specialKey(".", KeyType.PERIOD),
            specialKey("\u23CE", KeyType.ENTER)
        )
        val keyW4 = (w - keyGap * (row4Keys.size + 1)) / row4Keys.size.toFloat()
        val spaceW = keyW4 * 2 + keyGap // Space takes 2 slots
        var cx = x + keyGap
        var drawIdx = 0
        for (key in row4Keys) {
            val kw = if (key.type == KeyType.SPACE) spaceW else keyW4
            val keyRect = RectF(cx, cy, cx + kw, cy + rowHeight)
            keyRects[drawIdx] = keyRect
            drawKeyRect(canvas, keyRect, key)
            cx += kw + keyGap
            drawIdx++
        }

        // Row 5 is swallowed by row 4 structure — this is fine for the 5-row layout
    }

    private fun drawKeyRow(canvas: Canvas, x: Float, y: Float, w: Float, h: Float, keys: List<Key>) {
        val gap = keyGap.toFloat()
        val keyWidth = (w - gap * (keys.size + 1)) / keys.size
        var cx = x + gap
        for ((i, key) in keys.withIndex()) {
            val rect = RectF(cx, y, cx + keyWidth, y + h)
            keyRects[i] = rect
            drawKeyRect(canvas, rect, key)
            cx += keyWidth + gap
        }
    }

    private fun drawKeyRowWithSpecials(canvas: Canvas, x: Float, y: Float, w: Float, h: Float, keys: List<Key>) {
        val gap = keyGap.toFloat()
        val totalGap = gap * (keys.size + 1)
        val avail = w - totalGap
        val stdWidth = avail / keys.size
        var cx = x + gap
        for ((i, key) in keys.withIndex()) {
            val kw = when (key.type) {
                KeyType.BACKSPACE -> stdWidth * 1.5f
                KeyType.SHIFT -> stdWidth * 1.3f
                else -> stdWidth
            }
            val rect = RectF(cx, y, cx + kw, y + h)
            keyRects[i] = rect
            drawKeyRect(canvas, rect, key)
            cx += kw + gap
        }
    }

    private fun drawKeyRect(canvas: Canvas, rect: RectF, key: Key) {
        keyPaint.color = Color.WHITE
        keyPaint.style = Paint.Style.FILL
        canvas.drawRoundRect(rect, keyRadius, keyRadius, keyPaint)

        val label = when {
            key.type == KeyType.CHARACTER && isUpperCase -> key.label.uppercase(Locale.ROOT)
            else -> key.label
        }

        keyTextPaint.textSize = when (key.type) {
            KeyType.SPACE -> 10f * density
            KeyType.BACKSPACE, KeyType.ENTER, KeyType.SHIFT -> 16f * density
            else -> 14f * density
        }
        keyTextPaint.color = when (key.type) {
            KeyType.BACKSPACE, KeyType.ENTER, KeyType.SHIFT, KeyType.SYMBOL ->
                Color.parseColor("#5F6368")
            KeyType.SPACE -> Color.parseColor("#80868B")
            else -> Color.parseColor("#202124")
        }

        canvas.drawText(label, rect.centerX(), rect.centerY() + 5f * density, keyTextPaint)
    }

    private fun letter(c: String) = Key(KeyType.CHARACTER, c, null, c[0].code)
    private fun specialKey(label: String, type: KeyType) = Key(type, label, null, 0)

    // Layout

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredHeight = (toolbarHeight + candidateHeight + statusBarHeight +
                (48f * density * 5 + keyGap * 6).toInt())
        val h = resolveSize(desiredHeight, heightMeasureSpec)
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), h)
    }

    // Touch

    private var trackingKeyIndex: Int = -1

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val x = event.x
        val y = event.y

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                // Check toolbar
                for ((rect, action) in toolbarActions) {
                    if (rect.contains(x.toInt(), y.toInt())) {
                        listener?.onToolbarAction(action)
                        return true
                    }
                }
                // Check candidates
                for ((i, rect) in candidateRects.withIndex()) {
                    if (rect.contains(x.toInt(), y.toInt())) {
                        listener?.onCandidateSelected(i)
                        return true
                    }
                }
                // Check keys
                for ((idx, rect) in keyRects) {
                    if (rect.contains(x, y)) {
                        trackingKeyIndex = idx
                        invalidate()
                        return true
                    }
                }
            }
            MotionEvent.ACTION_UP -> {
                if (trackingKeyIndex >= 0) {
                    val keys = getCurrentKeys()
                    if (trackingKeyIndex < keys.size) {
                        listener?.onKey(keys[trackingKeyIndex])
                    }
                    trackingKeyIndex = -1
                    invalidate()
                    return true
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                trackingKeyIndex = -1
                invalidate()
            }
        }
        return true
    }

    private fun getCurrentKeys(): List<Key> {
        // Build flat list matching draw order
        val result = mutableListOf<Key>()
        result.addAll(qwertyRows[0].map { letter(it) })
        result.addAll(qwertyRows[1].map { letter(it) })
        result.addAll(listOf(specialKey("Shift", KeyType.SHIFT)) +
                qwertyRows[2].map { letter(it) } +
                listOf(specialKey("\u232B", KeyType.BACKSPACE)))
        result.addAll(listOf(
            specialKey("?123", KeyType.SYMBOL),
            specialKey(",", KeyType.COMMA),
            Key(KeyType.SPACE, "space", null, ' '.code),
            specialKey(".", KeyType.PERIOD),
            specialKey("\u23CE", KeyType.ENTER)
        ))
        return result
    }
}
