package com.knowsayin.android.rime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class RimeAssetValidationTest {

    private val assetDir = File("src/main/assets/rime")

    // -- Required files exist --

    @Test
    fun `dictionary file exists`() {
        val dict = File(assetDir, "pinyin_simp.dict.yaml")
        assertTrue("Missing pinyin_simp.dict.yaml", dict.isFile)
        assertTrue("Dictionary file is empty", dict.length() > 0)
    }

    @Test
    fun `schema file exists`() {
        val schema = File(assetDir, "knowsayin_pinyin.schema.yaml")
        assertTrue("Missing knowsayin_pinyin.schema.yaml", schema.isFile)
        assertTrue("Schema file is empty", schema.length() > 0)
    }

    @Test
    fun `NOTICE file exists`() {
        val notice = File(assetDir, "NOTICE")
        assertTrue("Missing NOTICE", notice.isFile)
        assertTrue("NOTICE file is empty", notice.length() > 0)
    }

    @Test
    fun `Apache license file exists`() {
        val license = File(assetDir, "LICENSE.apache-2.0")
        assertTrue("Missing LICENSE.apache-2.0", license.isFile)
        assertTrue("License file is empty", license.length() > 0)
    }

    @Test
    fun `ASSET_VERSION file exists`() {
        val versionFile = File(assetDir, "ASSET_VERSION")
        assertTrue("Missing ASSET_VERSION", versionFile.isFile)
        assertEquals("ASSET_VERSION must be 2", "2", versionFile.readText().trim())
    }

    @Test
    fun `default preset file exists`() {
        val preset = File(assetDir, "default.yaml")
        assertTrue("Missing default.yaml", preset.isFile)
        assertTrue("default.yaml must select knowsayin_pinyin", preset.readText().contains("schema: knowsayin_pinyin"))
    }

    @Test
    fun `symbols preset file exists`() {
        val preset = File(assetDir, "symbols.yaml")
        assertTrue("Missing symbols.yaml", preset.isFile)
        assertTrue("symbols.yaml must define punctuator", preset.readText().contains("punctuator:"))
    }

    // -- Schema references pinyin_simp --

    @Test
    fun `schema references pinyin_simp dictionary`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertTrue(
            "Schema must reference dictionary pinyin_simp",
            schemaText.contains("dictionary: pinyin_simp")
        )
    }

    @Test
    fun `schema enables pinyin completion sentence composition and user learning`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        val requiredOptions = listOf(
            "enable_completion: true",
            "enable_word_completion: true",
            "enable_sentence: true",
            "enable_user_dict: true"
        )
        val missing = requiredOptions.filterNot { schemaText.contains(it) }
        assertTrue(
            "Schema is missing real IME translator options: $missing",
            missing.isEmpty()
        )
    }

    @Test
    fun `schema uses schema_id knowsayin_pinyin`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertTrue(
            "Schema must use schema_id knowsayin_pinyin",
            schemaText.contains("schema_id: knowsayin_pinyin")
        )
    }

    // -- Schema does not mention prohibited terms --

    private val prohibitedTerms = listOf(
        "stroke", "reverse_lookup", "essay", "simplifier",
        "opencc", "OpenCC", "custom_phrase",
        "brise", "rime_ice", "oh-my-rime", "plum",
        "octagram", "trime", "Trime"
    )

    @Test
    fun `schema does not contain prohibited terms`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        val found = mutableListOf<String>()
        for (term in prohibitedTerms) {
            if (schemaText.contains(term, ignoreCase = true)) {
                found.add(term)
            }
        }
        assertTrue(
            "Schema contains prohibited terms: $found",
            found.isEmpty()
        )
    }

    // -- Asset directory does not contain prohibited filenames/patterns --

    private val prohibitedPatterns = listOf(
        "essay", "stroke", "brise", "rime-ice", "rime_ice",
        "oh-my-rime", "plum", "octagram", "trime",
        "reverse_lookup", "simplifier", "opencc", "custom_phrase"
    )

    @Test
    fun `asset directory does not contain prohibited filenames`() {
        val allFiles = assetDir.walkTopDown().filter { it.isFile }.map { it.name }.toList()
        val hits = mutableListOf<String>()
        for (file in allFiles) {
            for (pattern in prohibitedPatterns) {
                if (file.contains(pattern, ignoreCase = true)) {
                    hits.add("$file (matched '$pattern')")
                }
            }
        }
        assertTrue("Prohibited filenames found: $hits", hits.isEmpty())
    }

    @Test
    fun `asset directory does not contain prohibited content in any file`() {
        val gplTerms = listOf("GPL", "LGPL", "GNU General Public", "GNU Lesser General")
        val hits = mutableListOf<String>()
        assetDir.walkTopDown().filter { it.isFile }.forEach { file ->
            val text = file.readText()
            for (term in gplTerms) {
                if (text.contains(term)) {
                    hits.add("${file.name}: found '$term'")
                }
            }
        }
        // NOTICE and LICENSE files reference GPL/LGPL for exclusion context; skip them
        val acceptableHits = hits.filter { hit ->
            val name = hit.substringBefore(":")
            name != "NOTICE" && name != "LICENSE.apache-2.0"
        }
        assertTrue(
            "GPL/LGPL references outside NOTICE/LICENSE: $acceptableHits",
            acceptableHits.isEmpty()
        )
    }

    // -- Runtime YAML/dict assets are free of prohibited Rime terms --

    private val runtimeYamlFiles by lazy {
        assetDir.walkTopDown().filter { it.isFile && it.extension == "yaml" }
            .filter { it.name != "NOTICE" && it.name != "LICENSE.apache-2.0" }
            .toList()
    }

    @Test
    fun `runtime YAML assets do not contain prohibited Rime terms`() {
        val prohibitedYamlTerms = listOf(
            "stroke", "reverse_lookup", "essay", "simplifier",
            "opencc", "custom_phrase",
            "brise", "rime-ice", "rime_ice",
            "oh-my-rime", "plum", "octagram",
            "trime"
        )
        val hits = mutableListOf<String>()
        for (file in runtimeYamlFiles) {
            val text = file.readText()
            for (term in prohibitedYamlTerms) {
                if (text.contains(term, ignoreCase = true)) {
                    hits.add("${file.name}: found '$term'")
                }
            }
        }
        assertTrue(
            "Runtime YAML/dict assets contain prohibited Rime terms: $hits",
            hits.isEmpty()
        )
    }

    @Test
    fun `runtime YAML assets do not contain GPL or LGPL references`() {
        val gplTerms = listOf("GPL", "LGPL", "GNU General Public", "GNU Lesser General")
        val hits = mutableListOf<String>()
        for (file in runtimeYamlFiles) {
            val text = file.readText()
            for (term in gplTerms) {
                if (text.contains(term)) {
                    hits.add("${file.name}: found '$term'")
                }
            }
        }
        assertTrue(
            "Runtime YAML/dict assets contain GPL/LGPL references (only NOTICE may mention LGPL for marisa-trie dual-license): $hits",
            hits.isEmpty()
        )
    }

    // -- NOTICE and license checks --

    @Test
    fun `NOTICE mentions rime-pinyin-simp and Apache-2_0`() {
        val noticeText = File(assetDir, "NOTICE").readText()
        assertTrue("NOTICE must mention rime-pinyin-simp", noticeText.contains("rime-pinyin-simp"))
        assertTrue("NOTICE must mention Apache 2.0", noticeText.contains("Apache License 2.0"))
        assertTrue("NOTICE must mention librime", noticeText.contains("librime"))
    }

    @Test
    fun `NOTICE mentions BSD election for marisa-trie`() {
        val noticeText = File(assetDir, "NOTICE").readText()
        assertTrue(
            "NOTICE must document BSD-2-Clause election for marisa-trie",
            noticeText.contains("BSD 2-Clause") && noticeText.contains("marisa-trie")
        )
    }

    @Test
    fun `Apache license file contains expected header`() {
        val licenseText = File(assetDir, "LICENSE.apache-2.0").readText()
        assertTrue(
            "LICENSE.apache-2.0 must contain Apache License header",
            licenseText.contains("Apache License") &&
                licenseText.contains("Version 2.0")
        )
    }

    // -- Dictionary header check --

    @Test
    fun `dictionary YAML header is valid`() {
        val dictText = File(assetDir, "pinyin_simp.dict.yaml").readText()
        assertTrue("Dictionary must declare name pinyin_simp", dictText.contains("name: pinyin_simp"))
        assertTrue("Dictionary must have version", dictText.contains("version:"))
        assertTrue("Dictionary must mention AOSP origin", dictText.contains("android open source project"))
    }

    // -- Schema structure checks --

    @Test
    fun `schema uses script_translator`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertTrue("Schema must use script_translator", schemaText.contains("script_translator"))
    }

    @Test
    fun `schema imports default key_binder preset`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertTrue(
            "Schema must import default preset for key_binder",
            schemaText.contains("import_preset: default")
        )
    }

    @Test
    fun `schema imports symbols preset for punctuator`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertTrue(
            "Schema must import symbols preset for punctuator",
            schemaText.contains("import_preset: symbols")
        )
    }

    // -- Schema algebra rules --

    @Test
    fun `schema uses upstream pinyin algebra rules`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        val requiredRules = listOf(
            "abbrev/^([a-z]).+$/$1/",
            "abbrev/^([zcs]h).+$/$1/",
            "derive/^([nl])ue$/$1ve/",
            "derive/^([jqxy])u/$1v/",
            "erase/^hm$/",
            "erase/^ng$/"
        )
        val missing = mutableListOf<String>()
        for (rule in requiredRules) {
            if (!schemaText.contains(rule)) {
                missing.add(rule)
            }
        }
        assertTrue(
            "Schema is missing required upstream algebra rules: $missing",
            missing.isEmpty()
        )
    }

    @Test
    fun `schema does not contain unsafe xform simplification rule`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        assertFalse(
            "Schema must not contain the unsafe xform simplification rule",
            schemaText.contains("xform/^([a-z]+).*$/$1/")
        )
    }

    @Test
    fun `schema does not contain any xform algebra rules`() {
        val schemaText = File(assetDir, "knowsayin_pinyin.schema.yaml").readText()
        val xformCount = schemaText.lines().count { it.trim().startsWith("- xform/") }
        assertEquals(
            "Schema must have zero xform algebra rules (only erase/abbrev/derive should be used)",
            0, xformCount
        )
    }

    // -- Dictionary multi-syllable check --

    @Test
    fun `dictionary contains multi-syllable pinyin entries`() {
        val dictLines = File(assetDir, "pinyin_simp.dict.yaml").readLines()
        val multiSyllable = dictLines.filter { line ->
            line.contains('\t') && Regex("\\s").findAll(line.substringAfter('\t').substringBefore('\t')).count() >= 1
        }
        assertTrue(
            "Dictionary must contain multi-syllable pinyin entries (e.g., 'ba ba')",
            multiSyllable.isNotEmpty()
        )
        val baba = dictLines.any { it.contains("\tba ba\t") }
        assertTrue(
            "Dictionary must contain a 'ba ba' multi-syllable entry to guard against over-simplification",
            baba
        )
    }
}
