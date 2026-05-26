package com.knowsayin.android.keyboard

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import java.util.Locale

private const val CANDIDATE_MAX_VISIBLE = 5
private const val CANDIDATE_MIN_ITEM_WIDTH_DP = 52f
private const val CANDIDATE_TEXT_PADDING_DP = 8f

internal data class CandidateStripItem(val originalIndex: Int, val text: String, val widthDp: Float)

internal fun candidateStripItems(
    candidates: List<String>,
    composition: String,
    availableWidthDp: Float,
    textWidthDp: (String) -> Float
): List<CandidateStripItem> {
    val source = when {
        candidates.isNotEmpty() -> candidates
        composition.isNotBlank() -> listOf(composition)
        else -> return emptyList()
    }
    val available = availableWidthDp.coerceAtLeast(0f)
    if (available <= 0f) return emptyList()

    val measured = source.take(CANDIDATE_MAX_VISIBLE).mapIndexed { index, text ->
        MeasuredCandidateStripItem(
            originalIndex = index,
            text = text,
            desiredWidthDp = (textWidthDp(text) + CANDIDATE_TEXT_PADDING_DP * 2f)
                .coerceAtLeast(CANDIDATE_MIN_ITEM_WIDTH_DP)
        )
    }
    val first = measured.first()
    val displayed = mutableListOf(
        CandidateStripItem(
            originalIndex = first.originalIndex,
            text = first.text,
            widthDp = first.desiredWidthDp.coerceAtMost(available)
        )
    )

    var remaining = available - displayed.first().widthDp
    for (item in measured.drop(1)) {
        if (displayed.size >= CANDIDATE_MAX_VISIBLE) break
        if (item.desiredWidthDp > remaining) break
        displayed += CandidateStripItem(item.originalIndex, item.text, item.desiredWidthDp)
        remaining -= item.desiredWidthDp
    }

    return displayed
}

private data class MeasuredCandidateStripItem(
    val originalIndex: Int,
    val text: String,
    val desiredWidthDp: Float
)

class KeyboardView(context: Context) : View(context) {

    interface OnKeyboardActionListener {
        fun onKey(key: Key)
        fun onCandidateSelected(index: Int)
        fun onCandidatePage(forward: Boolean)
        fun onToolbarAction(action: ToolbarAction)
        fun onSpaceVoiceHoldStarted() {}
        fun onSpaceVoiceHoldReleased(heldAfterStartMs: Long) {}
        fun onSpaceVoiceHoldCancelled() {}
    }

    enum class ToolbarAction {
        OPTIMIZE,
        MICROPHONE,
        UNDO,
        TOGGLE_CN_EN,
        SETTINGS,
        HIDE_KEYBOARD,
        SWITCH_IME,
        SEND,
        CLEAR_COMPOSITION,
        MORE,
        EMOJI
    }

    enum class KeyType {
        CHARACTER,
        TEXT,
        SPACE,
        BACKSPACE,
        ENTER,
        SHIFT,
        SYMBOL,
        ALPHABET,
        SYMBOL_PAGE,
        TOGGLE_CN_EN,
        COMMA,
        PERIOD
    }

    data class Key(
        val type: KeyType,
        val label: String,
        val subLabel: String? = null,
        val code: Int = 0,
        val output: String? = null,
        val primary: Boolean = false
    )

    var listener: OnKeyboardActionListener? = null
    var isUpperCase: Boolean = false
    var isChineseMode: Boolean = true
    var isSymbolMode: Boolean = false
    var symbolPage: Int = 0

    var candidates: List<String> = emptyList()
        set(value) {
            val hadActiveComposition = hasActiveComposition()
            field = value
            requestLayoutIfCompositionVisibilityChanged(hadActiveComposition)
        }
    var composition: String = ""
        set(value) {
            val hadActiveComposition = hasActiveComposition()
            field = value
            requestLayoutIfCompositionVisibilityChanged(hadActiveComposition)
        }
    var highlightedCandidateIndex: Int = 0
    var canPageBackward: Boolean = false
    var canPageForward: Boolean = false
    var statusText: String = ""

    private data class KeyHit(val key: Key, val rect: RectF, val index: Int)
    private data class ActionHit(val action: ToolbarAction, val rect: RectF, val enabled: Boolean = true)
    private data class CandidateHit(val index: Int, val rect: RectF)
    private data class PageHit(val forward: Boolean, val rect: RectF, val enabled: Boolean)

    private val keyHits = mutableListOf<KeyHit>()
    private val actionHits = mutableListOf<ActionHit>()
    private val candidateHits = mutableListOf<CandidateHit>()
    private val pageHits = mutableListOf<PageHit>()
    private var pressedKeyIndex: Int = -1
    private var trackingKeyIndex: Int = -1
    private var backspaceRepeatStarted: Boolean = false
    private var backspaceRepeatKeyIndex: Int = -1
    private var spaceLongPressTriggered: Boolean = false
    private var spaceLongPressKeyIndex: Int = -1
    private var spaceVoiceHoldStartedAtMs: Long = 0L
    private val backspaceRepeatStarter = Runnable {
        val hit = activeBackspaceHit() ?: return@Runnable
        backspaceRepeatStarted = true
        listener?.onKey(hit.key)
        postDelayed(backspaceRepeatStep, BACKSPACE_REPEAT_INTERVAL_MS)
    }
    private val backspaceRepeatStep = object : Runnable {
        override fun run() {
            val hit = activeBackspaceHit() ?: return
            listener?.onKey(hit.key)
            postDelayed(this, BACKSPACE_REPEAT_INTERVAL_MS)
        }
    }
    private val spaceLongPressStarter = Runnable {
        val hit = activeSpaceHit() ?: return@Runnable
        spaceLongPressTriggered = true
        spaceVoiceHoldStartedAtMs = SystemClock.uptimeMillis()
        listener?.onSpaceVoiceHoldStarted()
    }

    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.DEFAULT
    }
    companion object {
        private const val COLOR_BG = "#202020"
        private const val COLOR_TOP_BG = "#191919"
        private const val COLOR_KEY = "#626262"
        private const val COLOR_KEY_PRESSED = "#757575"
        private const val COLOR_SPECIAL_KEY = "#303030"
        private const val COLOR_SPECIAL_PRESSED = "#3C3C3C"
        private const val COLOR_KEY_SHADOW = "#111111"
        private const val COLOR_TEXT = "#F5F5F5"
        private const val COLOR_MUTED = "#A8A8A8"
        private const val COLOR_TOOL = "#3A3A3A"
        private const val COLOR_SEND = "#10C86F"
        private const val COLOR_BLUE_KEY = "#4E83F7"

        private const val TOP_BAR_HEIGHT_DP = 48f
        private const val SECONDARY_ROW_HEIGHT_DP = 46f
        private const val KEY_HEIGHT_DP = 54f
        private const val KEY_GAP_DP = 5f
        private const val ROW_GAP_DP = 8f
        private const val KEYBOARD_TOP_PADDING_DP = 6f
        private const val BOTTOM_INSET_DP = 34f
        private const val KEY_RADIUS_DP = 8f
        private const val BACKSPACE_REPEAT_START_DELAY_MS = 350L
        private const val BACKSPACE_REPEAT_INTERVAL_MS = 55L
        private const val SPACE_LONG_PRESS_DELAY_MS = 450L
    }

    private val density: Float get() = resources.displayMetrics.density
    private fun dp(value: Float): Float = value * density

    private val topBarHeight: Int get() = dp(TOP_BAR_HEIGHT_DP).toInt()
    private val secondaryRowHeight: Int get() = dp(SECONDARY_ROW_HEIGHT_DP).toInt()
    private val keyHeight: Float get() = dp(KEY_HEIGHT_DP)
    private val keyGap: Float get() = dp(KEY_GAP_DP)
    private val rowGap: Float get() = dp(ROW_GAP_DP)
    private val keyboardTopPadding: Float get() = dp(KEYBOARD_TOP_PADDING_DP)
    private val bottomInset: Int get() = dp(BOTTOM_INSET_DP).toInt()
    private val keyRadius: Float get() = dp(KEY_RADIUS_DP)

    private val qwertyRows = listOf(
        listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
        listOf("a", "s", "d", "f", "g", "h", "j", "k", "l"),
        listOf("z", "x", "c", "v", "b", "n", "m")
    )

    private val symbolRowsPrimary = listOf(
        listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
        listOf("-", "/", ":", "~", "(", ")", "...", "@", "\"", "'"),
        listOf("。", "，", "、", "?", "!", ".")
    )

    private val symbolRowsSecondary = listOf(
        listOf("[", "]", "{", "}", "#", "%", "^", "*", "+", "="),
        listOf("_", "\\", "|", "<", ">", "\$", "&", "·", "“", "”"),
        listOf("；", "：", "《", "》", "？", "！")
    )

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        fillPaint.color = Color.parseColor(COLOR_BG)
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), fillPaint)

        keyHits.clear()
        actionHits.clear()
        candidateHits.clear()
        pageHits.clear()

        var y = 0f
        drawTopAccessory(canvas, y, width.toFloat(), topBarHeight.toFloat())
        y += topBarHeight

        if (hasActiveComposition()) {
            drawCandidateStrip(canvas, y, width.toFloat(), secondaryRowHeight.toFloat())
            y += secondaryRowHeight
        }

        drawKeyboard(canvas, y, width.toFloat(), height - y)
    }

    private fun hasActiveComposition(): Boolean {
        return composition.isNotBlank() || candidates.isNotEmpty()
    }

    private fun requestLayoutIfCompositionVisibilityChanged(hadActiveComposition: Boolean) {
        if (hadActiveComposition != hasActiveComposition()) {
            requestLayout()
        }
    }

    private fun drawTopAccessory(canvas: Canvas, y: Float, w: Float, h: Float) {
        fillPaint.color = Color.parseColor(COLOR_TOP_BG)
        canvas.drawRect(0f, y, w, y + h, fillPaint)

        val centerY = y + h / 2f
        val circleRadius = dp(17f)
        val iconColor = Color.parseColor(COLOR_TEXT)
        val mutedColor = Color.parseColor(COLOR_MUTED)
        val active = hasActiveComposition()

        val sidePadding = dp(9f)
        val leftStep = dp(40f)
        var leftCenterX = sidePadding + circleRadius
        val leftActions = listOf(
            ToolbarAction.OPTIMIZE,
            ToolbarAction.UNDO,
            ToolbarAction.TOGGLE_CN_EN
        )
        for (action in leftActions) {
            val rect = RectF(
                leftCenterX - circleRadius,
                centerY - circleRadius,
                leftCenterX + circleRadius,
                centerY + circleRadius
            )
            drawToolCircle(canvas, rect, action)
            leftCenterX += leftStep
        }

        val rightPadding = dp(8f)
        val sendWidth = dp(56f)
        val sendHeight = dp(34f)
        val rightCircleDiameter = circleRadius * 2f
        val sendRect = RectF(
            w - rightPadding - sendWidth,
            centerY - sendHeight / 2f,
            w - rightPadding,
            centerY + sendHeight / 2f
        )
        val settingsRect = RectF(
            w - rightPadding - rightCircleDiameter,
            centerY - circleRadius,
            w - rightPadding,
            centerY + circleRadius
        )
        val trailingControlLeft = if (active) sendRect.left else settingsRect.left

        if (statusText.isNotBlank()) {
            val statusLeft = (leftCenterX - leftStep / 2f + dp(22f)).coerceAtLeast(sidePadding)
            val statusRight = trailingControlLeft - dp(12f)
            val statusWidth = statusRight - statusLeft
            if (statusWidth > dp(34f)) {
                textPaint.color = mutedColor
                textPaint.textSize = dp(13f)
                textPaint.typeface = Typeface.DEFAULT
                val label = ellipsizeEnd(statusText, statusWidth, textPaint)
                val baseline = centerY - (textPaint.fontMetrics.ascent + textPaint.fontMetrics.descent) / 2f
                textPaint.textAlign = Paint.Align.LEFT
                canvas.drawText(label, statusLeft, baseline, textPaint)
                textPaint.textAlign = Paint.Align.CENTER
            }
        }

        if (active) {
            drawSendButton(canvas, sendRect)
        } else {
            drawCircleButton(canvas, settingsRect, ToolbarAction.SETTINGS, outlined = true) {
                drawGearIcon(canvas, settingsRect, iconColor)
            }
        }
    }

    private fun ellipsizeEnd(text: String, maxWidth: Float, paint: Paint): String {
        if (paint.measureText(text) <= maxWidth) return text
        val ellipsis = "..."
        val ellipsisWidth = paint.measureText(ellipsis)
        if (ellipsisWidth >= maxWidth) return ""
        val count = paint.breakText(text, true, maxWidth - ellipsisWidth, null)
        return text.take(count).trimEnd() + ellipsis
    }

    private fun drawSendButton(canvas: Canvas, rect: RectF) {
        fillPaint.color = Color.parseColor(COLOR_SEND)
        canvas.drawRoundRect(rect, dp(17f), dp(17f), fillPaint)
        actionHits.add(ActionHit(ToolbarAction.SEND, RectF(rect)))

        textPaint.color = Color.WHITE
        textPaint.textSize = dp(16f)
        textPaint.typeface = Typeface.DEFAULT_BOLD
        canvas.drawText("Send", rect.centerX(), centerTextBaseline(rect, textPaint), textPaint)
        textPaint.typeface = Typeface.DEFAULT
    }

    private inline fun drawCircleButton(
        canvas: Canvas,
        rect: RectF,
        action: ToolbarAction,
        outlined: Boolean,
        drawIcon: () -> Unit
    ) {
        actionHits.add(ActionHit(action, RectF(rect)))
        if (outlined) {
            strokePaint.color = Color.parseColor(COLOR_TEXT)
            strokePaint.strokeWidth = dp(1.6f)
            canvas.drawOval(rect, strokePaint)
        } else {
            fillPaint.color = Color.parseColor(COLOR_TOOL)
            canvas.drawOval(rect, fillPaint)
        }
        drawIcon()
    }

    private fun drawToolCircle(canvas: Canvas, rect: RectF, action: ToolbarAction) {
        actionHits.add(ActionHit(action, RectF(rect)))
        fillPaint.color = Color.parseColor(COLOR_TOOL)
        canvas.drawOval(rect, fillPaint)

        val color = Color.parseColor(COLOR_MUTED)
        when (action) {
            ToolbarAction.OPTIMIZE -> drawOptimizeIcon(canvas, rect, color)
            ToolbarAction.MICROPHONE -> drawVoiceWaveIcon(canvas, rect.centerX(), rect.centerY(), 0.82f, color)
            ToolbarAction.UNDO -> drawUndoIcon(canvas, rect, color)
            ToolbarAction.TOGGLE_CN_EN -> drawCnEnIcon(canvas, rect, color)
            ToolbarAction.SETTINGS -> drawGearIcon(canvas, rect, color)
            ToolbarAction.MORE -> drawBubbleIcon(canvas, rect, color)
            ToolbarAction.HIDE_KEYBOARD -> drawChevronDown(canvas, rect.centerX(), rect.centerY(), dp(11f), color)
            else -> {}
        }
    }

    private fun drawCandidateStrip(canvas: Canvas, y: Float, w: Float, h: Float) {
        fillPaint.color = Color.parseColor(COLOR_BG)
        canvas.drawRect(0f, y, w, y + h, fillPaint)

        val centerY = y + h / 2f
        val xButtonWidth = dp(44f)
        val pageButtonWidth = dp(32f)
        var left = dp(10f)
        var right = w - xButtonWidth

        if (canPageBackward) {
            val rect = RectF(0f, y, pageButtonWidth, y + h)
            pageHits.add(PageHit(forward = false, rect = RectF(rect), enabled = true))
            drawChevronLeft(canvas, rect.centerX(), centerY, dp(8f), Color.parseColor(COLOR_TEXT))
            left = pageButtonWidth
        }
        if (canPageForward) {
            val rect = RectF(right - pageButtonWidth, y, right, y + h)
            pageHits.add(PageHit(forward = true, rect = RectF(rect), enabled = true))
            drawChevronRight(canvas, rect.centerX(), centerY, dp(8f), Color.parseColor(COLOR_TEXT))
            right -= pageButtonWidth
        }

        val clearRect = RectF(w - xButtonWidth, y, w, y + h)
        actionHits.add(ActionHit(ToolbarAction.CLEAR_COMPOSITION, RectF(clearRect)))
        drawXIcon(canvas, clearRect.centerX(), clearRect.centerY(), dp(10f), Color.parseColor(COLOR_TEXT))

        val availableWidth = (right - left).coerceAtLeast(0f)
        val textPadding = dp(CANDIDATE_TEXT_PADDING_DP)
        textPaint.typeface = Typeface.DEFAULT
        textPaint.textSize = dp(22f)
        textPaint.textAlign = Paint.Align.CENTER
        val displayed = candidateStripItems(candidates, composition, availableWidth / density) { text ->
            textPaint.measureText(text) / density
        }
        if (displayed.isEmpty() || availableWidth <= 0f) return

        var candidateLeft = left
        for ((position, candidate) in displayed.withIndex()) {
            val candidateRight = (candidateLeft + dp(candidate.widthDp)).coerceAtMost(right)
            val rect = RectF(candidateLeft, y, candidateRight, y + h)
            if (rect.width() <= 0f) break

            candidateHits.add(CandidateHit(candidate.originalIndex, RectF(rect)))
            if (candidate.originalIndex == highlightedCandidateIndex) {
                fillPaint.color = Color.parseColor("#292929")
                val highlightRect = RectF(
                    rect.left + dp(3f),
                    rect.top + dp(8f),
                    rect.right - dp(3f),
                    rect.bottom - dp(8f)
                )
                if (highlightRect.width() > 0f && highlightRect.height() > 0f) {
                    canvas.drawRoundRect(highlightRect, dp(8f), dp(8f), fillPaint)
                }
            }

            textPaint.color = Color.parseColor(COLOR_TEXT)
            val textRect = RectF(rect.left + textPadding, rect.top, rect.right - textPadding, rect.bottom)
            if (textRect.width() > 0f) {
                val label = ellipsizeEnd(candidate.text, textRect.width(), textPaint)
                if (label.isNotEmpty()) {
                    val saveCount = canvas.save()
                    canvas.clipRect(textRect)
                    canvas.drawText(label, rect.centerX(), centerTextBaseline(rect, textPaint), textPaint)
                    canvas.restoreToCount(saveCount)
                }
            }

            if (position < displayed.lastIndex) {
                strokePaint.color = Color.parseColor("#3A3A3A")
                strokePaint.strokeWidth = dp(0.7f)
                canvas.drawLine(rect.right, y + dp(13f), rect.right, y + h - dp(13f), strokePaint)
            }
            candidateLeft = candidateRight
        }
    }

    private fun drawKeyboard(canvas: Canvas, y: Float, w: Float, h: Float) {
        fillPaint.color = Color.parseColor(COLOR_BG)
        canvas.drawRect(0f, y, w, y + h, fillPaint)

        val cy = y + keyboardTopPadding
        if (isSymbolMode) {
            drawSymbolKeyboard(canvas, cy, w)
        } else {
            drawAlphabetKeyboard(canvas, cy, w)
        }

        drawBottomBar(canvas, y + h - bottomInset, w, bottomInset.toFloat())
    }

    private fun drawAlphabetKeyboard(canvas: Canvas, y: Float, w: Float) {
        var cy = y
        drawEvenRow(canvas, cy, w, qwertyRows[0].map { letter(it) })
        cy += keyHeight + rowGap

        val row2Inset = dp(24f)
        drawEvenRow(canvas, cy, w - row2Inset * 2f, qwertyRows[1].map { letter(it) }, row2Inset)
        cy += keyHeight + rowGap

        val row3 = listOf(specialKey("shift", KeyType.SHIFT)) +
            qwertyRows[2].map { letter(it) } +
            listOf(specialKey("backspace", KeyType.BACKSPACE))
        val row3Weights = listOf(1.35f) + List(qwertyRows[2].size) { 1f } + listOf(1.35f)
        drawWeightedRow(canvas, cy, w, row3, row3Weights)
        cy += keyHeight + rowGap

        val bottomKeys = listOf(
            specialKey("123", KeyType.SYMBOL),
            Key(KeyType.COMMA, ",", "，", ','.code),
            Key(KeyType.SPACE, "space", null, ' '.code),
            Key(KeyType.TOGGLE_CN_EN, "中", "英"),
            specialKey("换行", KeyType.ENTER)
        )
        drawWeightedRow(canvas, cy, w, bottomKeys, listOf(2.0f, 1.0f, 3.8f, 1.0f, 2.1f))
    }

    private fun drawSymbolKeyboard(canvas: Canvas, y: Float, w: Float) {
        val rows = if (symbolPage % 2 == 0) symbolRowsPrimary else symbolRowsSecondary
        var cy = y
        drawEvenRow(canvas, cy, w, rows[0].map { textKey(it) })
        cy += keyHeight + rowGap

        drawEvenRow(canvas, cy, w, rows[1].map { textKey(it) })
        cy += keyHeight + rowGap

        val row3 = listOf(specialKey("符号", KeyType.SYMBOL_PAGE)) +
            rows[2].map { textKey(it) } +
            listOf(specialKey("backspace", KeyType.BACKSPACE))
        drawWeightedRow(canvas, cy, w, row3, listOf(1.35f) + List(rows[2].size) { 1f } + listOf(1.35f))
        cy += keyHeight + rowGap

        val bottomKeys = listOf(
            Key(KeyType.ALPHABET, "ABC", primary = true),
            Key(KeyType.SYMBOL_PAGE, "12", "34"),
            Key(KeyType.SPACE, "space", null, ' '.code),
            specialKey("换行", KeyType.ENTER)
        )
        drawWeightedRow(canvas, cy, w, bottomKeys, listOf(1.75f, 1.0f, 4.7f, 2.0f))
    }

    private fun drawEvenRow(
        canvas: Canvas,
        y: Float,
        w: Float,
        keys: List<Key>,
        xOffset: Float = 0f
    ) {
        val keyWidth = (w - keyGap * (keys.size + 1)) / keys.size
        var cx = xOffset + keyGap
        for (key in keys) {
            val rect = RectF(cx, y, cx + keyWidth, y + keyHeight)
            drawKey(canvas, rect, key)
            cx += keyWidth + keyGap
        }
    }

    private fun drawWeightedRow(canvas: Canvas, y: Float, w: Float, keys: List<Key>, weights: List<Float>) {
        val totalWeight = weights.sum().coerceAtLeast(1f)
        val baseWidth = (w - keyGap * (keys.size + 1)) / totalWeight
        var cx = keyGap
        for ((index, key) in keys.withIndex()) {
            val rect = RectF(cx, y, cx + baseWidth * weights[index], y + keyHeight)
            drawKey(canvas, rect, key)
            cx = rect.right + keyGap
        }
    }

    private fun drawKey(canvas: Canvas, rect: RectF, key: Key) {
        val index = keyHits.size
        keyHits.add(KeyHit(key, RectF(rect), index))

        val special = isSpecialKey(key)
        val pressed = pressedKeyIndex == index
        val baseColor = when {
            key.primary -> COLOR_BLUE_KEY
            special && pressed -> COLOR_SPECIAL_PRESSED
            special -> COLOR_SPECIAL_KEY
            pressed -> COLOR_KEY_PRESSED
            else -> COLOR_KEY
        }

        fillPaint.color = Color.parseColor(COLOR_KEY_SHADOW)
        canvas.drawRoundRect(
            RectF(rect.left, rect.top + dp(2f), rect.right, rect.bottom + dp(2f)),
            keyRadius,
            keyRadius,
            fillPaint
        )
        fillPaint.color = Color.parseColor(baseColor)
        canvas.drawRoundRect(rect, keyRadius, keyRadius, fillPaint)

        when (key.type) {
            KeyType.SHIFT -> drawShiftIcon(canvas, rect, isUpperCase)
            KeyType.BACKSPACE -> drawBackspaceIcon(canvas, rect)
            KeyType.SPACE -> drawSpaceWave(canvas, rect)
            KeyType.ALPHABET -> drawAlphabetReturn(canvas, rect)
            KeyType.SYMBOL_PAGE -> drawStackedText(canvas, rect, key.label, key.subLabel, Color.parseColor(COLOR_TEXT))
            KeyType.TOGGLE_CN_EN -> drawStackedText(canvas, rect, key.label, key.subLabel, Color.parseColor(COLOR_TEXT))
            KeyType.COMMA -> drawStackedText(canvas, rect, key.label, key.subLabel, Color.parseColor(COLOR_TEXT))
            KeyType.TEXT, KeyType.CHARACTER, KeyType.PERIOD, KeyType.SYMBOL, KeyType.ENTER ->
                drawKeyText(canvas, rect, key)
        }
    }

    private fun drawKeyText(canvas: Canvas, rect: RectF, key: Key) {
        textPaint.typeface = Typeface.DEFAULT
        textPaint.color = Color.parseColor(COLOR_TEXT)
        textPaint.textSize = when (key.type) {
            KeyType.CHARACTER -> dp(27f)
            KeyType.ENTER -> dp(20f)
            KeyType.SYMBOL -> dp(18f)
            else -> dp(24f)
        }
        val label = if (key.type == KeyType.CHARACTER) {
            key.label.uppercase(Locale.ROOT)
        } else {
            key.label
        }
        canvas.drawText(label, rect.centerX(), centerTextBaseline(rect, textPaint), textPaint)
    }

    private fun drawStackedText(canvas: Canvas, rect: RectF, top: String, bottom: String?, color: Int) {
        textPaint.typeface = Typeface.DEFAULT
        textPaint.color = color
        textPaint.textSize = dp(18f)
        val topY = rect.centerY() - dp(4f)
        canvas.drawText(top, rect.centerX(), topY, textPaint)
        if (bottom != null) {
            textPaint.color = Color.parseColor(COLOR_MUTED)
            textPaint.textSize = dp(15f)
            canvas.drawText(bottom, rect.centerX(), rect.centerY() + dp(17f), textPaint)
        }
    }

    private fun drawAlphabetReturn(canvas: Canvas, rect: RectF) {
        strokePaint.color = Color.WHITE
        strokePaint.strokeWidth = dp(2.2f)
        val cy = rect.centerY()
        val x1 = rect.centerX() - dp(9f)
        val x2 = rect.centerX() + dp(10f)
        canvas.drawLine(x1, cy, x2, cy, strokePaint)
        canvas.drawLine(x1, cy, x1 + dp(8f), cy - dp(8f), strokePaint)
        canvas.drawLine(x1, cy, x1 + dp(8f), cy + dp(8f), strokePaint)
    }

    private fun drawShiftIcon(canvas: Canvas, rect: RectF, active: Boolean) {
        strokePaint.color = Color.WHITE
        strokePaint.strokeWidth = dp(if (active) 2.4f else 2.0f)
        fillPaint.color = if (active) Color.WHITE else Color.TRANSPARENT
        val path = Path()
        val cx = rect.centerX()
        val top = rect.top + rect.height() * 0.34f
        val midY = rect.top + rect.height() * 0.55f
        val left = cx - dp(13f)
        val right = cx + dp(13f)
        val stemLeft = cx - dp(6f)
        val stemRight = cx + dp(6f)
        val bottom = rect.top + rect.height() * 0.73f
        path.moveTo(cx, top)
        path.lineTo(right, midY)
        path.lineTo(stemRight, midY)
        path.lineTo(stemRight, bottom)
        path.lineTo(stemLeft, bottom)
        path.lineTo(stemLeft, midY)
        path.lineTo(left, midY)
        path.close()
        if (active) {
            canvas.drawPath(path, fillPaint)
        } else {
            canvas.drawPath(path, strokePaint)
        }
    }

    private fun drawBackspaceIcon(canvas: Canvas, rect: RectF) {
        strokePaint.color = Color.WHITE
        strokePaint.strokeWidth = dp(2.2f)
        val left = rect.centerX() - dp(15f)
        val right = rect.centerX() + dp(15f)
        val top = rect.centerY() - dp(9f)
        val bottom = rect.centerY() + dp(9f)
        val notch = left - dp(8f)
        val path = Path().apply {
            moveTo(left, top)
            lineTo(right, top)
            lineTo(right, bottom)
            lineTo(left, bottom)
            lineTo(notch, rect.centerY())
            close()
        }
        canvas.drawPath(path, strokePaint)
        drawXIcon(canvas, rect.centerX() + dp(4f), rect.centerY(), dp(5f), Color.WHITE)
    }

    private fun drawSpaceWave(canvas: Canvas, rect: RectF) {
        val color = Color.parseColor(COLOR_MUTED)
        strokePaint.color = color
        strokePaint.strokeWidth = dp(4f)
        val cx = rect.centerX()
        val cy = rect.centerY()
        val spacing = dp(7f)
        val heights = listOf(7f, 13f, 20f, 13f, 7f)
        for ((index, h) in heights.withIndex()) {
            val x = cx + (index - 2) * spacing
            canvas.drawLine(x, cy - dp(h) / 2f, x, cy + dp(h) / 2f, strokePaint)
        }
    }

    private fun drawBottomBar(canvas: Canvas, y: Float, w: Float, h: Float) {
        if (h <= 0f) return
        fillPaint.color = Color.parseColor(COLOR_BG)
        canvas.drawRect(0f, y, w, y + h, fillPaint)
        val centerY = y + h / 2f
        val hitSize = h.coerceAtLeast(dp(38f))
        val chevronCx = dp(66f)
        val globeCx = w - dp(66f)

        actionHits.add(
            ActionHit(
                ToolbarAction.HIDE_KEYBOARD,
                RectF(
                    chevronCx - hitSize / 2f,
                    centerY - hitSize / 2f,
                    chevronCx + hitSize / 2f,
                    centerY + hitSize / 2f
                )
            )
        )
        actionHits.add(
            ActionHit(
                ToolbarAction.SWITCH_IME,
                RectF(
                    globeCx - hitSize / 2f,
                    centerY - hitSize / 2f,
                    globeCx + hitSize / 2f,
                    centerY + hitSize / 2f
                )
            )
        )

        drawChevronDown(canvas, chevronCx, centerY, dp(8f), Color.WHITE)
        drawGlobeIcon(canvas, globeCx, centerY, dp(11f), Color.WHITE)
        strokePaint.color = Color.WHITE
        strokePaint.strokeWidth = dp(3.5f)
        canvas.drawLine(w * 0.39f, y + h - dp(8f), w * 0.61f, y + h - dp(8f), strokePaint)
    }

    private fun isSpecialKey(key: Key): Boolean {
        return key.type in setOf(
            KeyType.BACKSPACE,
            KeyType.ENTER,
            KeyType.SHIFT,
            KeyType.SYMBOL,
            KeyType.ALPHABET,
            KeyType.SYMBOL_PAGE,
            KeyType.TOGGLE_CN_EN
        )
    }

    private fun letter(c: String) = Key(KeyType.CHARACTER, c, null, c[0].code)
    private fun textKey(label: String) = Key(KeyType.TEXT, label, output = label)
    private fun specialKey(label: String, type: KeyType) = Key(type, label)

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val candidateStripHeight = if (hasActiveComposition()) secondaryRowHeight else 0
        val desiredHeight = topBarHeight +
            candidateStripHeight +
            keyboardTopPadding.toInt() +
            (keyHeight * 4f).toInt() +
            (rowGap * 3f).toInt() +
            bottomInset
        val h = resolveSize(desiredHeight, heightMeasureSpec)
        setMeasuredDimension(MeasureSpec.getSize(widthMeasureSpec), h)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val x = event.x
        val y = event.y

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                for (hit in actionHits.asReversed()) {
                    if (hit.enabled && hit.rect.contains(x, y)) {
                        listener?.onToolbarAction(hit.action)
                        return true
                    }
                }
                for (hit in pageHits.asReversed()) {
                    if (hit.enabled && hit.rect.contains(x, y)) {
                        listener?.onCandidatePage(hit.forward)
                        return true
                    }
                }
                for (hit in candidateHits.asReversed()) {
                    if (hit.rect.contains(x, y)) {
                        listener?.onCandidateSelected(hit.index)
                        return true
                    }
                }
                for (hit in keyHits.asReversed()) {
                    if (hit.rect.contains(x, y)) {
                        trackingKeyIndex = hit.index
                        pressedKeyIndex = hit.index
                        if (hit.key.type == KeyType.BACKSPACE) {
                            startBackspaceRepeat(hit.index)
                        } else if (hit.key.type == KeyType.SPACE) {
                            startSpaceLongPress(hit.index)
                        }
                        invalidate()
                        return true
                    }
                }
            }

            MotionEvent.ACTION_MOVE -> {
                val index = trackingKeyIndex
                if (index >= 0) {
                    val hit = keyHits.firstOrNull { it.index == index }
                    val stillInside = hit != null && hit.rect.contains(x, y)
                    if (!stillInside) {
                        cancelTrackedKey()
                        return true
                    }
                }
            }

            MotionEvent.ACTION_UP -> {
                val index = trackingKeyIndex
                val didBackspaceRepeat = backspaceRepeatStarted
                val didSpaceLongPress = releaseSpaceLongPress(event.eventTime)
                stopBackspaceRepeat()
                if (index >= 0) {
                    val hit = keyHits.firstOrNull { it.index == index }
                    trackingKeyIndex = -1
                    pressedKeyIndex = -1
                    invalidate()
                    if (hit != null && hit.rect.contains(x, y)) {
                        val suppressUpKey =
                            hit.key.type == KeyType.BACKSPACE && didBackspaceRepeat ||
                                hit.key.type == KeyType.SPACE && didSpaceLongPress
                        if (!suppressUpKey) {
                            listener?.onKey(hit.key)
                        }
                    }
                    return true
                }
            }

            MotionEvent.ACTION_CANCEL -> {
                cancelTrackedKey()
                return true
            }
        }
        return true
    }

    override fun onDetachedFromWindow() {
        cancelTrackedKey()
        super.onDetachedFromWindow()
    }

    private fun startBackspaceRepeat(index: Int) {
        stopBackspaceRepeat()
        backspaceRepeatKeyIndex = index
        postDelayed(backspaceRepeatStarter, BACKSPACE_REPEAT_START_DELAY_MS)
    }

    private fun stopBackspaceRepeat() {
        removeCallbacks(backspaceRepeatStarter)
        removeCallbacks(backspaceRepeatStep)
        backspaceRepeatStarted = false
        backspaceRepeatKeyIndex = -1
    }

    private fun startSpaceLongPress(index: Int) {
        resetSpaceLongPress(notifyCancel = false)
        spaceLongPressKeyIndex = index
        postDelayed(spaceLongPressStarter, SPACE_LONG_PRESS_DELAY_MS)
    }

    private fun releaseSpaceLongPress(eventTimeMs: Long): Boolean {
        removeCallbacks(spaceLongPressStarter)
        val didStart = spaceLongPressTriggered
        val heldAfterStartMs = if (spaceVoiceHoldStartedAtMs > 0L) {
            eventTimeMs - spaceVoiceHoldStartedAtMs
        } else {
            0L
        }
        spaceLongPressTriggered = false
        spaceLongPressKeyIndex = -1
        spaceVoiceHoldStartedAtMs = 0L
        if (didStart) {
            listener?.onSpaceVoiceHoldReleased(heldAfterStartMs.coerceAtLeast(0L))
        }
        return didStart
    }

    private fun resetSpaceLongPress(notifyCancel: Boolean) {
        removeCallbacks(spaceLongPressStarter)
        val didStart = spaceLongPressTriggered
        spaceLongPressTriggered = false
        spaceLongPressKeyIndex = -1
        spaceVoiceHoldStartedAtMs = 0L
        if (notifyCancel && didStart) {
            listener?.onSpaceVoiceHoldCancelled()
        }
    }

    private fun activeBackspaceHit(): KeyHit? {
        val index = backspaceRepeatKeyIndex
        if (index < 0 || trackingKeyIndex != index || pressedKeyIndex != index) return null
        val hit = keyHits.firstOrNull { it.index == index } ?: return null
        return hit.takeIf { it.key.type == KeyType.BACKSPACE }
    }

    private fun activeSpaceHit(): KeyHit? {
        val index = spaceLongPressKeyIndex
        if (index < 0 || trackingKeyIndex != index || pressedKeyIndex != index) return null
        val hit = keyHits.firstOrNull { it.index == index } ?: return null
        return hit.takeIf { it.key.type == KeyType.SPACE }
    }

    private fun cancelTrackedKey() {
        stopBackspaceRepeat()
        resetSpaceLongPress(notifyCancel = true)
        trackingKeyIndex = -1
        pressedKeyIndex = -1
        invalidate()
    }

    private fun centerTextBaseline(rect: RectF, paint: Paint): Float {
        val metrics = paint.fontMetrics
        return rect.centerY() - (metrics.ascent + metrics.descent) / 2f
    }

    private fun drawVoiceWaveIcon(canvas: Canvas, cx: Float, cy: Float, scale: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.2f) * scale
        val base = dp(5f) * scale
        canvas.drawLine(cx - base * 2.1f, cy - base * 0.8f, cx - base * 1.4f, cy, strokePaint)
        canvas.drawLine(cx - base * 2.1f, cy + base * 0.8f, cx - base * 1.4f, cy, strokePaint)
        for (i in 0..2) {
            val r = base * (1.5f + i * 1.15f)
            val rect = RectF(cx - r * 1.25f, cy - r, cx + r * 0.75f, cy + r)
            canvas.drawArc(rect, -42f, 84f, false, strokePaint)
        }
    }

    private fun drawOptimizeIcon(canvas: Canvas, rect: RectF, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2f)
        val cx = rect.centerX()
        val cy = rect.centerY()
        val r = dp(5f)
        canvas.drawRoundRect(RectF(cx - dp(13f), cy - r, cx - dp(3f), cy + r), r, r, strokePaint)
        canvas.drawRoundRect(RectF(cx + dp(3f), cy - r, cx + dp(13f), cy + r), r, r, strokePaint)
        canvas.drawRoundRect(RectF(cx - r, cy - dp(13f), cx + r, cy - dp(3f)), r, r, strokePaint)
        canvas.drawRoundRect(RectF(cx - r, cy + dp(3f), cx + r, cy + dp(13f)), r, r, strokePaint)
    }

    private fun drawUndoIcon(canvas: Canvas, rect: RectF, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.2f)
        val cx = rect.centerX()
        val cy = rect.centerY()
        val path = Path().apply {
            moveTo(cx - dp(11f), cy - dp(2f))
            cubicTo(cx - dp(4f), cy - dp(12f), cx + dp(14f), cy - dp(7f), cx + dp(10f), cy + dp(8f))
        }
        canvas.drawPath(path, strokePaint)
        canvas.drawLine(cx - dp(11f), cy - dp(2f), cx - dp(3f), cy - dp(9f), strokePaint)
        canvas.drawLine(cx - dp(11f), cy - dp(2f), cx - dp(2f), cy + dp(3f), strokePaint)
    }

    private fun drawCnEnIcon(canvas: Canvas, rect: RectF, color: Int) {
        textPaint.color = color
        textPaint.typeface = Typeface.DEFAULT_BOLD
        textPaint.textSize = dp(17f)
        canvas.drawText(if (isChineseMode) "中" else "EN", rect.centerX() - dp(3f), rect.centerY() + dp(2f), textPaint)
        textPaint.typeface = Typeface.DEFAULT
        textPaint.textSize = dp(13f)
        canvas.drawText(if (isChineseMode) "A" else "中", rect.centerX() + dp(11f), rect.centerY() + dp(12f), textPaint)
    }

    private fun drawGearIcon(canvas: Canvas, rect: RectF, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(1.9f)
        val cx = rect.centerX()
        val cy = rect.centerY()
        val hub = dp(3.3f)
        val body = dp(8.5f)
        val toothInner = dp(9.7f)
        val toothOuter = dp(13f)
        canvas.drawCircle(cx, cy, body, strokePaint)
        canvas.drawCircle(cx, cy, hub, strokePaint)
        strokePaint.strokeWidth = dp(2.3f)
        for (i in 0 until 8) {
            val angle = Math.toRadians((i * 45).toDouble())
            val x1 = cx + kotlin.math.cos(angle).toFloat() * toothInner
            val y1 = cy + kotlin.math.sin(angle).toFloat() * toothInner
            val x2 = cx + kotlin.math.cos(angle).toFloat() * toothOuter
            val y2 = cy + kotlin.math.sin(angle).toFloat() * toothOuter
            canvas.drawLine(x1, y1, x2, y2, strokePaint)
        }
    }

    private fun drawBubbleIcon(canvas: Canvas, rect: RectF, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2f)
        val bubble = RectF(rect.centerX() - dp(13f), rect.centerY() - dp(11f), rect.centerX() + dp(12f), rect.centerY() + dp(9f))
        canvas.drawRoundRect(bubble, dp(5f), dp(5f), strokePaint)
        canvas.drawLine(rect.centerX() - dp(2f), bubble.bottom, rect.centerX() - dp(7f), bubble.bottom + dp(5f), strokePaint)
        canvas.drawLine(rect.centerX() + dp(1f), bubble.bottom, rect.centerX() - dp(7f), bubble.bottom + dp(5f), strokePaint)
        canvas.drawLine(rect.centerX() + dp(5f), rect.centerY() - dp(5f), rect.centerX() - dp(1f), rect.centerY() + dp(5f), strokePaint)
    }

    private fun drawChevronDown(canvas: Canvas, cx: Float, cy: Float, size: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.2f)
        canvas.drawLine(cx - size, cy - size * 0.45f, cx, cy + size * 0.55f, strokePaint)
        canvas.drawLine(cx + size, cy - size * 0.45f, cx, cy + size * 0.55f, strokePaint)
    }

    private fun drawChevronLeft(canvas: Canvas, cx: Float, cy: Float, size: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.2f)
        canvas.drawLine(cx + size * 0.5f, cy - size, cx - size * 0.5f, cy, strokePaint)
        canvas.drawLine(cx + size * 0.5f, cy + size, cx - size * 0.5f, cy, strokePaint)
    }

    private fun drawChevronRight(canvas: Canvas, cx: Float, cy: Float, size: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.2f)
        canvas.drawLine(cx - size * 0.5f, cy - size, cx + size * 0.5f, cy, strokePaint)
        canvas.drawLine(cx - size * 0.5f, cy + size, cx + size * 0.5f, cy, strokePaint)
    }

    private fun drawXIcon(canvas: Canvas, cx: Float, cy: Float, size: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2.6f)
        canvas.drawLine(cx - size, cy - size, cx + size, cy + size, strokePaint)
        canvas.drawLine(cx + size, cy - size, cx - size, cy + size, strokePaint)
    }

    private fun drawGlobeIcon(canvas: Canvas, cx: Float, cy: Float, radius: Float, color: Int) {
        strokePaint.color = color
        strokePaint.strokeWidth = dp(2f)
        val rect = RectF(cx - radius, cy - radius, cx + radius, cy + radius)
        canvas.drawOval(rect, strokePaint)
        canvas.drawLine(cx - radius, cy, cx + radius, cy, strokePaint)
        canvas.drawArc(RectF(cx - radius * 0.55f, cy - radius, cx + radius * 0.55f, cy + radius), 90f, 180f, false, strokePaint)
        canvas.drawArc(RectF(cx - radius * 0.55f, cy - radius, cx + radius * 0.55f, cy + radius), -90f, 180f, false, strokePaint)
    }
}
