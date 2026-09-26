#pragma once

#include <arboresce/arboresce.h>
#include <cstdint>
#include <string_view>

namespace arboresce {

enum class status : std::uint32_t {
    ok = ARBORESCE_OK,
    invalid_argument = ARBORESCE_INVALID_ARGUMENT,
    panic = ARBORESCE_PANIC
};

struct name_result {
    status code;
    std::string_view value;

    explicit operator bool() const noexcept { return code == status::ok; }
};

[[nodiscard]] inline name_result name() noexcept {
    arboresce_string_view raw{};
    const auto code = static_cast<status>(arboresce_v1_name(&raw));
    if (code != status::ok) {
        return {code, {}};
    }
    return {code, raw.len == 0 ? std::string_view{}
                               : std::string_view{raw.data, raw.len}};
}

[[nodiscard]] inline status print_name() noexcept {
    return static_cast<status>(arboresce_v1_print_name());
}

}
