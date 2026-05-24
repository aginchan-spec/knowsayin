cmake_minimum_required(VERSION 3.22.1)
project("knowsayin-rime")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(
    knowsayin-rime
    SHARED
    native-lib.cpp
    rime_jni.cpp
)

target_include_directories(
    knowsayin-rime
    PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_compile_definitions(
    knowsayin-rime
    PRIVATE
    TARGET_ABI="${CMAKE_ANDROID_ARCH_ABI}"
)

target_link_libraries(
    knowsayin-rime
    android
    log
)
