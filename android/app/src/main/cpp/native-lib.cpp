#include <jni.h>
#include <rime_api.h>
#include <string>

#define STRINGIFY_IMPL(x) #x
#define STRINGIFY(x) STRINGIFY_IMPL(x)

extern "C" {

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetVersion(
    JNIEnv* env,
    jclass /* clazz */) {
    RimeApi* rime = rime_get_api();
    const char* version = nullptr;
    if (RIME_API_AVAILABLE(rime, get_version)) {
        version = rime->get_version();
    }

    std::string result = "librime-linked";
    if (version != nullptr && version[0] != '\0') {
        result += "-";
        result += version;
    }
    return env->NewStringUTF(result.c_str());
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
