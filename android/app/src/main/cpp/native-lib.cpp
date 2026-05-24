#include <jni.h>
#include <string>

#define STRINGIFY_IMPL(x) #x
#define STRINGIFY(x) STRINGIFY_IMPL(x)

extern "C" {

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetVersion(
    JNIEnv* env,
    jclass /* clazz */) {
    return env->NewStringUTF("librime-stub-0.1.0");
}

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetBuildInfo(
    JNIEnv* env,
    jclass /* clazz */) {
    return env->NewStringUTF(
        "KnowSayin Rime JNI Bridge\n"
        "NDK: " STRINGIFY(__NDK_MAJOR__) "." STRINGIFY(__NDK_MINOR__) "." STRINGIFY(__NDK_BETA__) "\n"
        "ABI: " TARGET_ABI "\n"
        "C++ Standard: C++17"
    );
}

} // extern "C"
