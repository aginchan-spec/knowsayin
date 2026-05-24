#include <jni.h>
#include <string>
#include <android/log.h>

#define TAG "knowsayin-rime-jni"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

extern "C" {

// --- Lifecycle ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeInitialize(
    JNIEnv* env, jclass clazz,
    jstring dataDir, jstring sharedDataDir) {
    LOGD("nativeInitialize (stub)");
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeFinalize(
    JNIEnv* env, jclass clazz) {
    LOGD("nativeFinalize (stub)");
    return JNI_TRUE;
}

// --- Session ---

JNIEXPORT jlong JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeCreateSession(
    JNIEnv* env, jclass clazz) {
    LOGD("nativeCreateSession (stub)");
    return 1L;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeDestroySession(
    JNIEnv* env, jclass clazz, jlong sessionId) {
    LOGD("nativeDestroySession (stub)");
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSessionExists(
    JNIEnv* env, jclass clazz, jlong sessionId) {
    return JNI_TRUE;
}

// --- Input ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeProcessKey(
    JNIEnv* env, jclass clazz,
    jlong sessionId, jint keycode, jint mask) {
    LOGD("nativeProcessKey (stub)");
    return JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSimulateKeySequence(
    JNIEnv* env, jclass clazz,
    jlong sessionId, jstring sequence) {
    LOGD("nativeSimulateKeySequence (stub)");
    return JNI_FALSE;
}

// --- Context ---

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetContext(
    JNIEnv* env, jclass clazz, jlong sessionId) {
    return env->NewStringUTF("{}");
}

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetCommit(
    JNIEnv* env, jclass clazz, jlong sessionId) {
    return nullptr;
}

// --- Candidate ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSelectCandidate(
    JNIEnv* env, jclass clazz,
    jlong sessionId, jint index) {
    LOGD("nativeSelectCandidate (stub)");
    return JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeHighlightCandidate(
    JNIEnv* env, jclass clazz,
    jlong sessionId, jint index) {
    return JNI_FALSE;
}

// --- Config ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSetOption(
    JNIEnv* env, jclass clazz,
    jlong sessionId, jstring option, jboolean value) {
    LOGD("nativeSetOption (stub)");
    return JNI_FALSE;
}

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetProperty(
    JNIEnv* env, jclass clazz, jstring name) {
    return nullptr;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeLoadSchema(
    JNIEnv* env, jclass clazz, jstring schemaId) {
    LOGD("nativeLoadSchema (stub)");
    return JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeConfigure(
    JNIEnv* env, jclass clazz,
    jstring key, jstring value) {
    LOGD("nativeConfigure (stub)");
    return JNI_FALSE;
}

// --- Maintenance ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeStartMaintenance(
    JNIEnv* env, jclass clazz, jboolean fullCheck) {
    LOGD("nativeStartMaintenance (stub)");
    return JNI_FALSE;
}

} // extern "C"
