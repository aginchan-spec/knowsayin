#include <jni.h>
#include <android/input.h>
#include <android/keycodes.h>
#include <android/log.h>
#include <rime_api.h>

#include <cstring>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_set>

#define TAG "knowsayin-rime-jni"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

namespace {

constexpr const char* kDefaultSchema = "knowsayin_pinyin";

constexpr int kRimeShiftMask = 1 << 0;
constexpr int kRimeControlMask = 1 << 2;
constexpr int kRimeAltMask = 1 << 3;
constexpr int kRimeSuperMask = 1 << 26;
constexpr int kRimeMetaMask = 1 << 28;

constexpr int XK_BackSpace = 0xff08;
constexpr int XK_Tab = 0xff09;
constexpr int XK_Return = 0xff0d;
constexpr int XK_Escape = 0xff1b;
constexpr int XK_Home = 0xff50;
constexpr int XK_Left = 0xff51;
constexpr int XK_Up = 0xff52;
constexpr int XK_Right = 0xff53;
constexpr int XK_Down = 0xff54;
constexpr int XK_Page_Up = 0xff55;
constexpr int XK_Page_Down = 0xff56;
constexpr int XK_End = 0xff57;
constexpr int XK_Delete = 0xffff;

std::mutex g_mutex;
bool g_initialized = false;
std::string g_user_data_dir;
std::string g_shared_data_dir;
std::string g_default_schema = kDefaultSchema;
std::unordered_set<RimeSessionId> g_sessions;

class ScopedUtfChars {
public:
    ScopedUtfChars(JNIEnv* env, jstring value) : env_(env), value_(value) {
        if (env_ != nullptr && value_ != nullptr) {
            chars_ = env_->GetStringUTFChars(value_, nullptr);
        }
    }

    ~ScopedUtfChars() {
        if (env_ != nullptr && value_ != nullptr && chars_ != nullptr) {
            env_->ReleaseStringUTFChars(value_, chars_);
        }
    }

    std::string str() const {
        return std::string(chars_ != nullptr ? chars_ : "");
    }

private:
    JNIEnv* env_;
    jstring value_;
    const char* chars_ = nullptr;
};

RimeApi* api() {
    return rime_get_api();
}

void fillTraits(RimeTraits* traits) {
    traits->shared_data_dir = g_shared_data_dir.c_str();
    traits->user_data_dir = g_user_data_dir.c_str();
    traits->distribution_name = "KnowSayin";
    traits->distribution_code_name = "knowsayin";
    traits->distribution_version = "0.1.0";
    traits->app_name = "rime.knowsayin.android";
    traits->min_log_level = 2;
    traits->log_dir = "";
}

void finalizeLocked(RimeApi* rime) {
    if (rime == nullptr || !g_initialized) {
        g_sessions.clear();
        g_initialized = false;
        return;
    }

    if (RIME_API_AVAILABLE(rime, cleanup_all_sessions)) {
        rime->cleanup_all_sessions();
    } else if (RIME_API_AVAILABLE(rime, destroy_session)) {
        for (RimeSessionId session : g_sessions) {
            rime->destroy_session(session);
        }
    }
    g_sessions.clear();

    if (RIME_API_AVAILABLE(rime, finalize)) {
        rime->finalize();
    }
    g_initialized = false;
}

std::string jsonString(const char* value) {
    std::string out;
    out.reserve(value == nullptr ? 2 : std::strlen(value) + 2);
    out.push_back('"');
    if (value != nullptr) {
        for (const unsigned char* p = reinterpret_cast<const unsigned char*>(value); *p; ++p) {
            switch (*p) {
                case '"':
                    out += "\\\"";
                    break;
                case '\\':
                    out += "\\\\";
                    break;
                case '\b':
                    out += "\\b";
                    break;
                case '\f':
                    out += "\\f";
                    break;
                case '\n':
                    out += "\\n";
                    break;
                case '\r':
                    out += "\\r";
                    break;
                case '\t':
                    out += "\\t";
                    break;
                default:
                    if (*p < 0x20) {
                        constexpr char hex[] = "0123456789abcdef";
                        out += "\\u00";
                        out.push_back(hex[*p >> 4]);
                        out.push_back(hex[*p & 0x0f]);
                    } else {
                        out.push_back(static_cast<char>(*p));
                    }
                    break;
            }
        }
    }
    out.push_back('"');
    return out;
}

std::string emptyContextJson() {
    return "{\"composition\":\"\",\"compositionCursor\":0,"
           "\"candidates\":[],\"highlightedIndex\":0,"
           "\"pageSize\":0,\"pageNumber\":0,\"isLastPage\":true,"
           "\"selectKeys\":\"\",\"isComposing\":false}";
}

int mapAndroidKeycodeToRime(int keycode) {
    switch (keycode) {
        case AKEYCODE_DEL:
            return XK_BackSpace;
        case AKEYCODE_FORWARD_DEL:
            return XK_Delete;
        case AKEYCODE_ENTER:
        case AKEYCODE_NUMPAD_ENTER:
            return XK_Return;
        case AKEYCODE_TAB:
            return XK_Tab;
        case AKEYCODE_ESCAPE:
            return XK_Escape;
        case AKEYCODE_SPACE:
            return ' ';
        case AKEYCODE_COMMA:
        case AKEYCODE_NUMPAD_COMMA:
            return ',';
        case AKEYCODE_PERIOD:
        case AKEYCODE_NUMPAD_DOT:
            return '.';
        case AKEYCODE_APOSTROPHE:
            return '\'';
        case AKEYCODE_SEMICOLON:
            return ';';
        case AKEYCODE_SLASH:
        case AKEYCODE_NUMPAD_DIVIDE:
            return '/';
        case AKEYCODE_MINUS:
        case AKEYCODE_NUMPAD_SUBTRACT:
            return '-';
        case AKEYCODE_EQUALS:
        case AKEYCODE_NUMPAD_EQUALS:
            return '=';
        case AKEYCODE_PLUS:
        case AKEYCODE_NUMPAD_ADD:
            return '+';
        case AKEYCODE_STAR:
        case AKEYCODE_NUMPAD_MULTIPLY:
            return '*';
        case AKEYCODE_POUND:
            return '#';
        case AKEYCODE_AT:
            return '@';
        case AKEYCODE_LEFT_BRACKET:
            return '[';
        case AKEYCODE_RIGHT_BRACKET:
            return ']';
        case AKEYCODE_BACKSLASH:
            return '\\';
        case AKEYCODE_GRAVE:
            return '`';
        case AKEYCODE_DPAD_LEFT:
            return XK_Left;
        case AKEYCODE_DPAD_UP:
            return XK_Up;
        case AKEYCODE_DPAD_RIGHT:
            return XK_Right;
        case AKEYCODE_DPAD_DOWN:
            return XK_Down;
        case AKEYCODE_MOVE_HOME:
            return XK_Home;
        case AKEYCODE_MOVE_END:
            return XK_End;
        case AKEYCODE_PAGE_UP:
            return XK_Page_Up;
        case AKEYCODE_PAGE_DOWN:
            return XK_Page_Down;
        default:
            break;
    }

    if (keycode >= 0x20 && keycode <= 0x7e) {
        return keycode;
    }
    if (keycode >= AKEYCODE_A && keycode <= AKEYCODE_Z) {
        return 'a' + (keycode - AKEYCODE_A);
    }
    if (keycode >= AKEYCODE_0 && keycode <= AKEYCODE_9) {
        return '0' + (keycode - AKEYCODE_0);
    }
    if (keycode >= AKEYCODE_NUMPAD_0 && keycode <= AKEYCODE_NUMPAD_9) {
        return '0' + (keycode - AKEYCODE_NUMPAD_0);
    }
    return keycode;
}

int mapAndroidMetaStateToRime(int mask) {
    int rimeMask = 0;
    if ((mask & (AMETA_SHIFT_ON | AMETA_SHIFT_LEFT_ON | AMETA_SHIFT_RIGHT_ON)) != 0) {
        rimeMask |= kRimeShiftMask;
    }
    if ((mask & (AMETA_CTRL_ON | AMETA_CTRL_LEFT_ON | AMETA_CTRL_RIGHT_ON)) != 0) {
        rimeMask |= kRimeControlMask;
    }
    if ((mask & (AMETA_ALT_ON | AMETA_ALT_LEFT_ON | AMETA_ALT_RIGHT_ON)) != 0) {
        rimeMask |= kRimeAltMask;
    }
    if ((mask & AMETA_META_ON) != 0) {
        rimeMask |= kRimeMetaMask;
    }
    if ((mask & (AMETA_META_LEFT_ON | AMETA_META_RIGHT_ON)) != 0) {
        rimeMask |= kRimeSuperMask;
    }
    return rimeMask;
}

jstring newNullableString(JNIEnv* env, const std::string& value) {
    return value.empty() ? nullptr : env->NewStringUTF(value.c_str());
}

bool schemaLooksLoadableLocked(RimeApi* rime, const std::string& schemaId) {
    if (rime == nullptr || schemaId.empty()) {
        return false;
    }
    if (!RIME_API_AVAILABLE(rime, schema_open) ||
        !RIME_API_AVAILABLE(rime, config_get_string) ||
        !RIME_API_AVAILABLE(rime, config_close)) {
        return true;
    }

    RimeConfig config = {0};
    if (!rime->schema_open(schemaId.c_str(), &config)) {
        return false;
    }
    char value[128] = {0};
    const bool ok = rime->config_get_string(
        &config, "schema/schema_id", value, sizeof(value));
    rime->config_close(&config);
    return ok && schemaId == value;
}

} // namespace

extern "C" {

// --- Lifecycle ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeInitialize(
    JNIEnv* env, jclass /* clazz */,
    jstring dataDir, jstring sharedDataDir) {
    try {
        ScopedUtfChars userDir(env, dataDir);
        ScopedUtfChars sharedDir(env, sharedDataDir);
        const std::string user = userDir.str();
        const std::string shared = sharedDir.str();
        if (user.empty() || shared.empty()) {
            LOGE("nativeInitialize missing data directories");
            return JNI_FALSE;
        }

        RimeApi* rime = api();
        if (rime == nullptr ||
            !RIME_API_AVAILABLE(rime, setup) ||
            !RIME_API_AVAILABLE(rime, initialize)) {
            LOGE("nativeInitialize missing required librime API");
            return JNI_FALSE;
        }

        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_initialized && g_user_data_dir == user && g_shared_data_dir == shared) {
            return JNI_TRUE;
        }
        if (g_initialized) {
            finalizeLocked(rime);
        }

        g_user_data_dir = user;
        g_shared_data_dir = shared;

        RIME_STRUCT(RimeTraits, traits);
        fillTraits(&traits);

        rime->setup(&traits);
        if (RIME_API_AVAILABLE(rime, set_notification_handler)) {
            rime->set_notification_handler(nullptr, nullptr);
        }

        rime->initialize(&traits);

        bool maintenanceOk = true;
        if (RIME_API_AVAILABLE(rime, start_maintenance)) {
            maintenanceOk = rime->start_maintenance(True) != False;
            if (maintenanceOk && RIME_API_AVAILABLE(rime, join_maintenance_thread)) {
                rime->join_maintenance_thread();
            }
        }
        if (!maintenanceOk && RIME_API_AVAILABLE(rime, deploy)) {
            maintenanceOk = rime->deploy() != False;
        }
        if (!maintenanceOk) {
            LOGE("nativeInitialize librime deployment failed");
            finalizeLocked(rime);
            return JNI_FALSE;
        }

        g_initialized = true;
        LOGD("nativeInitialize complete");
        return JNI_TRUE;
    } catch (...) {
        LOGE("nativeInitialize failed");
        return JNI_FALSE;
    }
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeFinalize(
    JNIEnv* /* env */, jclass /* clazz */) {
    std::lock_guard<std::mutex> lock(g_mutex);
    finalizeLocked(api());
    return JNI_TRUE;
}

// --- Session ---

JNIEXPORT jlong JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeCreateSession(
    JNIEnv* /* env */, jclass /* clazz */) {
    try {
        std::lock_guard<std::mutex> lock(g_mutex);
        RimeApi* rime = api();
        if (!g_initialized || rime == nullptr || !RIME_API_AVAILABLE(rime, create_session)) {
            return 0L;
        }
        RimeSessionId session = rime->create_session();
        if (!session) {
            return 0L;
        }
        if (!g_default_schema.empty() && RIME_API_AVAILABLE(rime, select_schema)) {
            rime->select_schema(session, g_default_schema.c_str());
        }
        g_sessions.insert(session);
        return static_cast<jlong>(session);
    } catch (...) {
        LOGE("nativeCreateSession failed");
        return 0L;
    }
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeDestroySession(
    JNIEnv* /* env */, jclass /* clazz */, jlong sessionId) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    const auto session = static_cast<RimeSessionId>(sessionId);
    if (rime == nullptr || !RIME_API_AVAILABLE(rime, destroy_session)) {
        g_sessions.erase(session);
        return JNI_FALSE;
    }
    const bool destroyed = rime->destroy_session(session) != False;
    g_sessions.erase(session);
    return destroyed ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSessionExists(
    JNIEnv* /* env */, jclass /* clazz */, jlong sessionId) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr || !RIME_API_AVAILABLE(rime, find_session)) {
        return JNI_FALSE;
    }
    return rime->find_session(static_cast<RimeSessionId>(sessionId)) ? JNI_TRUE : JNI_FALSE;
}

// --- Input ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeProcessKey(
    JNIEnv* /* env */, jclass /* clazz */,
    jlong sessionId, jint keycode, jint mask) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr || !RIME_API_AVAILABLE(rime, process_key)) {
        return JNI_FALSE;
    }
    const int rimeKeycode = mapAndroidKeycodeToRime(static_cast<int>(keycode));
    const int rimeMask = mapAndroidMetaStateToRime(static_cast<int>(mask));
    return rime->process_key(static_cast<RimeSessionId>(sessionId), rimeKeycode, rimeMask)
        ? JNI_TRUE
        : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSimulateKeySequence(
    JNIEnv* env, jclass /* clazz */,
    jlong sessionId, jstring sequence) {
    ScopedUtfChars chars(env, sequence);
    const std::string keys = chars.str();
    if (keys.empty()) {
        return JNI_FALSE;
    }

    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr) {
        return JNI_FALSE;
    }
    const auto session = static_cast<RimeSessionId>(sessionId);
    if (RIME_API_AVAILABLE(rime, simulate_key_sequence)) {
        return rime->simulate_key_sequence(session, keys.c_str()) ? JNI_TRUE : JNI_FALSE;
    }
    if (!RIME_API_AVAILABLE(rime, process_key)) {
        return JNI_FALSE;
    }
    bool processed = true;
    for (unsigned char ch : keys) {
        processed = rime->process_key(session, ch, 0) != False && processed;
    }
    return processed ? JNI_TRUE : JNI_FALSE;
}

// --- Context ---

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetContext(
    JNIEnv* env, jclass /* clazz */, jlong sessionId) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr ||
        !RIME_API_AVAILABLE(rime, get_context) ||
        !RIME_API_AVAILABLE(rime, free_context)) {
        return env->NewStringUTF(emptyContextJson().c_str());
    }

    RIME_STRUCT(RimeContext, context);
    if (!rime->get_context(static_cast<RimeSessionId>(sessionId), &context)) {
        return env->NewStringUTF(emptyContextJson().c_str());
    }

    std::ostringstream json;
    json << "{";
    json << "\"composition\":" << jsonString(context.composition.preedit) << ",";
    json << "\"compositionCursor\":" << context.composition.cursor_pos << ",";
    json << "\"pageSize\":" << context.menu.page_size << ",";
    json << "\"pageNumber\":" << context.menu.page_no << ",";
    json << "\"isLastPage\":" << (context.menu.is_last_page ? "true" : "false") << ",";
    json << "\"selectKeys\":" << jsonString(context.menu.select_keys) << ",";
    json << "\"candidates\":[";
    for (int i = 0; i < context.menu.num_candidates; ++i) {
        if (i > 0) {
            json << ",";
        }
        const RimeCandidate& candidate = context.menu.candidates[i];
        json << "{\"text\":" << jsonString(candidate.text)
             << ",\"comment\":" << jsonString(candidate.comment) << "}";
    }
    json << "],";
    json << "\"highlightedIndex\":" << context.menu.highlighted_candidate_index << ",";
    const bool isComposing =
        context.composition.length > 0 || context.menu.num_candidates > 0;
    json << "\"isComposing\":" << (isComposing ? "true" : "false");
    json << "}";

    const std::string result = json.str();
    rime->free_context(&context);
    return env->NewStringUTF(result.c_str());
}

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetCommit(
    JNIEnv* env, jclass /* clazz */, jlong sessionId) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr ||
        !RIME_API_AVAILABLE(rime, get_commit) ||
        !RIME_API_AVAILABLE(rime, free_commit)) {
        return nullptr;
    }
    RIME_STRUCT(RimeCommit, commit);
    if (!rime->get_commit(static_cast<RimeSessionId>(sessionId), &commit)) {
        return nullptr;
    }
    const std::string text = commit.text != nullptr ? commit.text : "";
    rime->free_commit(&commit);
    return newNullableString(env, text);
}

// --- Candidate ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSelectCandidate(
    JNIEnv* /* env */, jclass /* clazz */,
    jlong sessionId, jint index) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr) {
        return JNI_FALSE;
    }
    if (index < 0) {
        if (RIME_API_AVAILABLE(rime, clear_composition)) {
            rime->clear_composition(static_cast<RimeSessionId>(sessionId));
            return JNI_TRUE;
        }
        return JNI_FALSE;
    }
    if (RIME_API_AVAILABLE(rime, select_candidate_on_current_page)) {
        return rime->select_candidate_on_current_page(
            static_cast<RimeSessionId>(sessionId), static_cast<size_t>(index))
            ? JNI_TRUE
            : JNI_FALSE;
    }
    if (RIME_API_AVAILABLE(rime, select_candidate)) {
        return rime->select_candidate(
            static_cast<RimeSessionId>(sessionId), static_cast<size_t>(index))
            ? JNI_TRUE
            : JNI_FALSE;
    }
    return JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeHighlightCandidate(
    JNIEnv* /* env */, jclass /* clazz */, jlong sessionId, jint index) {
    if (index < 0) {
        return JNI_FALSE;
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr) {
        return JNI_FALSE;
    }
    if (RIME_API_AVAILABLE(rime, highlight_candidate_on_current_page)) {
        return rime->highlight_candidate_on_current_page(
            static_cast<RimeSessionId>(sessionId), static_cast<size_t>(index))
            ? JNI_TRUE
            : JNI_FALSE;
    }
    if (RIME_API_AVAILABLE(rime, highlight_candidate)) {
        return rime->highlight_candidate(
            static_cast<RimeSessionId>(sessionId), static_cast<size_t>(index))
            ? JNI_TRUE
            : JNI_FALSE;
    }
    return JNI_FALSE;
}

// --- Config ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeSetOption(
    JNIEnv* env, jclass /* clazz */,
    jlong sessionId, jstring option, jboolean value) {
    ScopedUtfChars optionChars(env, option);
    const std::string optionName = optionChars.str();
    if (optionName.empty()) {
        return JNI_FALSE;
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr || !RIME_API_AVAILABLE(rime, set_option)) {
        return JNI_FALSE;
    }
    rime->set_option(
        static_cast<RimeSessionId>(sessionId),
        optionName.c_str(),
        value == JNI_TRUE ? True : False);
    return JNI_TRUE;
}

JNIEXPORT jstring JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeGetProperty(
    JNIEnv* env, jclass /* clazz */, jstring name) {
    ScopedUtfChars nameChars(env, name);
    const std::string property = nameChars.str();
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (property == "defaultSchema") {
        return newNullableString(env, g_default_schema);
    }
    if (property == "initialized") {
        return env->NewStringUTF(g_initialized ? "true" : "false");
    }
    if (property == "version" && rime != nullptr && RIME_API_AVAILABLE(rime, get_version)) {
        const char* version = rime->get_version();
        return version != nullptr ? env->NewStringUTF(version) : nullptr;
    }
    if (property == "sharedDataDir") {
        return newNullableString(env, g_shared_data_dir);
    }
    if (property == "userDataDir") {
        return newNullableString(env, g_user_data_dir);
    }
    return nullptr;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeLoadSchema(
    JNIEnv* env, jclass /* clazz */, jstring schemaId) {
    ScopedUtfChars schemaChars(env, schemaId);
    const std::string schema = schemaChars.str();
    if (schema.empty()) {
        return JNI_FALSE;
    }

    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (g_initialized && !schemaLooksLoadableLocked(rime, schema)) {
        return JNI_FALSE;
    }
    g_default_schema = schema;
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeConfigure(
    JNIEnv* env, jclass /* clazz */,
    jstring key, jstring value) {
    ScopedUtfChars keyChars(env, key);
    ScopedUtfChars valueChars(env, value);
    const std::string configKey = keyChars.str();
    const std::string configValue = valueChars.str();
    if ((configKey == "schema" || configKey == "schemaId" ||
         configKey == "defaultSchema") && !configValue.empty()) {
        std::lock_guard<std::mutex> lock(g_mutex);
        RimeApi* rime = api();
        if (g_initialized && !schemaLooksLoadableLocked(rime, configValue)) {
            return JNI_FALSE;
        }
        g_default_schema = configValue;
        return JNI_TRUE;
    }
    return JNI_FALSE;
}

// --- Maintenance ---

JNIEXPORT jboolean JNICALL
Java_com_knowsayin_android_rime_RimeJniBridge_nativeStartMaintenance(
    JNIEnv* /* env */, jclass /* clazz */, jboolean fullCheck) {
    std::lock_guard<std::mutex> lock(g_mutex);
    RimeApi* rime = api();
    if (!g_initialized || rime == nullptr || !RIME_API_AVAILABLE(rime, start_maintenance)) {
        return JNI_FALSE;
    }
    const bool started = rime->start_maintenance(fullCheck == JNI_TRUE ? True : False) != False;
    if (started && RIME_API_AVAILABLE(rime, join_maintenance_thread)) {
        rime->join_maintenance_thread();
    }
    return started ? JNI_TRUE : JNI_FALSE;
}

} // extern "C"
