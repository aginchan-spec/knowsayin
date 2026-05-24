package com.knowsayin.android.cloud

import android.content.SharedPreferences
import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class KnowSayinCloudClient(private val prefs: SharedPreferences) {

    companion object {
        private const val TAG = "KnowSayinCloud"
        private const val BASE_URL = "https://api.knowsayin.com"
        private const val VERSION = "0.1.0"
        private const val USER_AGENT = "KnowSayin-Android/$VERSION"

        private const val PREF_TOKEN = "cloud_session_token"
        private const val PREF_DEVICE_CODE = "cloud_device_code"
    }

    fun getSessionToken(): String? = prefs.getString(PREF_TOKEN, null)

    fun getDeviceCode(): String? = prefs.getString(PREF_DEVICE_CODE, null)

    fun createSession(): Boolean {
        try {
            val response = post("$BASE_URL/v1/session", JSONObject())
            val token = response.optString("token", "")
            val deviceCode = response.optString("deviceCode", "")
            if (token.isNotEmpty()) {
                prefs.edit()
                    .putString(PREF_TOKEN, token)
                    .putString(PREF_DEVICE_CODE, deviceCode)
                    .apply()
                return true
            }
        } catch (e: Exception) {
            Log.e(TAG, "createSession failed: ${e.message}")
        }
        return false
    }

    fun getConfig(): JSONObject? {
        return try {
            val token = getSessionToken() ?: return null
            get("$BASE_URL/v1/config", token)
        } catch (e: Exception) {
            Log.e(TAG, "getConfig failed: ${e.message}")
            null
        }
    }

    fun getUsage(): JSONObject? {
        return try {
            val token = getSessionToken() ?: return null
            get("$BASE_URL/v1/usage", token)
        } catch (e: Exception) {
            Log.e(TAG, "getUsage failed: ${e.message}")
            null
        }
    }

    fun clean(text: String): CleanResult {
        val token = getSessionToken()
        if (token == null) {
            if (!createSession()) {
                return CleanResult.Error("no session")
            }
        }

        val sessionToken = getSessionToken() ?: return CleanResult.Error("no session")
        return try {
            val body = JSONObject().apply {
                put("text", text)
            }
            val response = post("$BASE_URL/v1/clean", body, sessionToken)
            val cleaned = response.optString("cleaned", "")
            if (cleaned.isNotEmpty()) {
                CleanResult.Success(cleaned)
            } else {
                val error = response.optString("error", "empty response")
                if (error.contains("quota", ignoreCase = true)) {
                    CleanResult.QuotaEmpty
                } else {
                    CleanResult.Error(error)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "clean failed: ${e.message}")
            CleanResult.Error(e.message ?: "network error")
        }
    }

    private fun get(url: String, token: String): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "GET"
            conn.setRequestProperty("User-Agent", USER_AGENT)
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.connectTimeout = 15000
            conn.readTimeout = 30000
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.let { s -> BufferedReader(InputStreamReader(s)).readText() } ?: "{}"
            return JSONObject(body)
        } finally {
            conn.disconnect()
        }
    }

    private fun post(url: String, body: JSONObject, token: String? = null): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.setRequestProperty("User-Agent", USER_AGENT)
            conn.setRequestProperty("Content-Type", "application/json")
            if (token != null) {
                conn.setRequestProperty("Authorization", "Bearer $token")
            }
            conn.doOutput = true
            conn.connectTimeout = 15000
            conn.readTimeout = 30000
            OutputStreamWriter(conn.outputStream).use { w -> w.write(body.toString()) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val responseBody = stream?.let { s -> BufferedReader(InputStreamReader(s)).readText() } ?: "{}"
            return JSONObject(responseBody)
        } finally {
            conn.disconnect()
        }
    }
}

sealed class CleanResult {
    data class Success(val text: String) : CleanResult()
    data class Error(val message: String) : CleanResult()
    data object QuotaEmpty : CleanResult()
}
