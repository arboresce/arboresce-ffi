cmake_minimum_required(VERSION 3.24)
project(ArboresceCpp VERSION 0.0.0 LANGUAGES C CXX)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include(CTest)
find_package(Arboresce CONFIG REQUIRED)
set(ARBORESCE_VERSION "${PROJECT_VERSION}" CACHE STRING "SDK version")
configure_package_config_file(cmake/ArboresceCppConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppConfig.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/ArboresceCpp"
    PATH_VARS CMAKE_INSTALL_INCLUDEDIR)
configure_file(cmake/ArboresceCppTargets.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppTargets.cmake" @ONLY)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppConfigVersion.cmake"
    VERSION "${ARBORESCE_VERSION}" COMPATIBILITY SameMajorVersion)
install(DIRECTORY include/ DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppTargets.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/ArboresceCppConfigVersion.cmake"
    DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/ArboresceCpp")
install(FILES LICENSE-MIT LICENSE-APACHE DESTINATION "${CMAKE_INSTALL_DATADIR}/arboresce-cpp")
file(READ README.md ARBORESCE_README)
string(REPLACE "../../DEVELOPERS.md" "DEVELOPERS.md" ARBORESCE_README "${ARBORESCE_README}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/README.md" "${ARBORESCE_README}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/README.md" ../../DEVELOPERS.md
    DESTINATION "${CMAKE_INSTALL_DATADIR}/arboresce-cpp")
if(BUILD_TESTING)
    find_package(Threads REQUIRED)
    foreach(linkage IN ITEMS shared static)
        add_executable(cpp_api_${linkage} tests/api.cpp)
        target_include_directories(cpp_api_${linkage} PRIVATE include)
        target_compile_features(cpp_api_${linkage} PRIVATE cxx_std_17)
        target_compile_options(cpp_api_${linkage} PRIVATE -Wall -Wextra -Werror -UNDEBUG)
        target_link_libraries(cpp_api_${linkage} PRIVATE Arboresce::c_${linkage} Threads::Threads)
        add_test(NAME cpp_api_${linkage} COMMAND cpp_api_${linkage})
    endforeach()
    add_executable(cpp_no_exceptions tests/no_exceptions.cpp tests/status_stub.c)
    target_include_directories(cpp_no_exceptions PRIVATE include "${ARBORESCE_INCLUDE_DIR}")
    target_compile_features(cpp_no_exceptions PRIVATE cxx_std_17 c_std_11)
    target_compile_options(cpp_no_exceptions PRIVATE -Wall -Wextra -Werror -UNDEBUG "$<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions>")
    target_compile_definitions(cpp_no_exceptions PRIVATE ARBORESCE_STATIC)
    add_test(NAME cpp_no_exceptions COMMAND cpp_no_exceptions)
endif()
