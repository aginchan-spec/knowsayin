package com.knowsayin.android.rime

import android.content.Context
import java.io.File
import java.io.FileNotFoundException

object RimeAssetManager {

    private const val ASSET_SOURCE = "rime"
    private const val CURRENT_VERSION = 2

    private const val DIR_SHARED = "shared"
    private const val DIR_USER = "user"
    private const val VERSION_FILE = "asset_version.txt"

    fun getSharedDir(context: Context): File =
        File(context.filesDir, "rime/$DIR_SHARED")

    fun getUserDir(context: Context): File =
        File(context.filesDir, "rime/$DIR_USER")

    fun extractIfNeeded(context: Context): Pair<File, File> {
        val userDir = getUserDir(context)
        val sharedDir = getSharedDir(context)

        val versionFile = File(userDir, VERSION_FILE)
        val installedVersion = if (versionFile.exists()) {
            versionFile.readText().trim().toIntOrNull() ?: 0
        } else {
            0
        }

        if (installedVersion < CURRENT_VERSION) {
            sharedDir.deleteRecursively()
            sharedDir.mkdirs()
            copyAssets(context, ASSET_SOURCE, sharedDir)
            userDir.mkdirs()
            versionFile.writeText(CURRENT_VERSION.toString())
        }

        return Pair(sharedDir, userDir)
    }

    private fun copyAssets(context: Context, path: String, target: File) {
        context.assets.list(path)?.forEach { name ->
            val child = File(target, name)
            val assetPath = "$path/$name"
            try {
                context.assets.open(assetPath).use { input ->
                    child.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
            } catch (e: FileNotFoundException) {
                child.mkdirs()
                copyAssets(context, assetPath, child)
            }
        }
    }
}
