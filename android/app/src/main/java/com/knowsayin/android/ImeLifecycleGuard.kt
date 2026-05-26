package com.knowsayin.android

class ImeLifecycleGuard {
    private var generation: Int = 0
    private var destroyed: Boolean = false

    fun currentToken(): Int = generation

    fun markInputChanged() {
        generation += 1
    }

    fun markDestroyed() {
        destroyed = true
        generation += 1
    }

    fun isCurrent(token: Int): Boolean {
        return !destroyed && token == generation
    }

    fun isDestroyed(): Boolean = destroyed
}
