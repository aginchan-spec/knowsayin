cmake_minimum_required(VERSION 3.22.1)
project("knowsayin-rime")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(KNOWSAYIN_RIME_ROOT "/home/dnachan/build/knowsayin-rime/install" CACHE PATH
    "Root directory containing per-ABI static librime install prefixes")

if(DEFINED ANDROID_ABI)
    set(KNOWSAYIN_RIME_ABI "${ANDROID_ABI}")
elseif(DEFINED CMAKE_ANDROID_ARCH_ABI)
    set(KNOWSAYIN_RIME_ABI "${CMAKE_ANDROID_ARCH_ABI}")
else()
    message(FATAL_ERROR "Unable to determine Android ABI for librime dependency prefix")
endif()

set(KNOWSAYIN_RIME_PREFIX "${KNOWSAYIN_RIME_ROOT}/${KNOWSAYIN_RIME_ABI}")

if(NOT IS_DIRECTORY "${KNOWSAYIN_RIME_PREFIX}")
    message(FATAL_ERROR
        "Missing librime dependency prefix for ABI ${KNOWSAYIN_RIME_ABI}: "
        "${KNOWSAYIN_RIME_PREFIX}. Build deps with android/scripts/build-librime-deps.sh "
        "or pass -DKNOWSAYIN_RIME_ROOT=/path/to/install.")
endif()

set(KNOWSAYIN_RIME_INCLUDE_DIR "${KNOWSAYIN_RIME_PREFIX}/include")
set(KNOWSAYIN_RIME_LIB_DIR "${KNOWSAYIN_RIME_PREFIX}/lib")

if(NOT EXISTS "${KNOWSAYIN_RIME_INCLUDE_DIR}/rime_api.h")
    message(FATAL_ERROR "Missing rime_api.h in ${KNOWSAYIN_RIME_INCLUDE_DIR}")
endif()

function(knowsayin_import_static_library target archive_name)
    set(archive_path "${KNOWSAYIN_RIME_LIB_DIR}/lib${archive_name}.a")
    if(NOT EXISTS "${archive_path}")
        message(FATAL_ERROR "Missing static library for ${KNOWSAYIN_RIME_ABI}: ${archive_path}")
    endif()
    add_library(${target} STATIC IMPORTED GLOBAL)
    set_target_properties(${target} PROPERTIES IMPORTED_LOCATION "${archive_path}")
endfunction()

knowsayin_import_static_library(rime_static rime)
knowsayin_import_static_library(leveldb_static leveldb)
knowsayin_import_static_library(marisa_static marisa)
knowsayin_import_static_library(opencc_static opencc)
knowsayin_import_static_library(snappy_static snappy)
knowsayin_import_static_library(yaml_cpp_static yaml-cpp)

message(STATUS "Linking librime static dependencies from ${KNOWSAYIN_RIME_PREFIX}")

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
    ${KNOWSAYIN_RIME_INCLUDE_DIR}
)

target_compile_definitions(
    knowsayin-rime
    PRIVATE
    TARGET_ABI="${KNOWSAYIN_RIME_ABI}"
    KNOWSAYIN_RIME_LINKED=1
)

target_link_libraries(
    knowsayin-rime
    "-Wl,--start-group"
    rime_static
    leveldb_static
    marisa_static
    opencc_static
    yaml_cpp_static
    "-Wl,--whole-archive"
    snappy_static
    "-Wl,--no-whole-archive"
    "-Wl,--end-group"
    android
    log
)
