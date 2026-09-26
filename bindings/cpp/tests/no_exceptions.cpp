#include <arboresce/arboresce.hpp>
#include <cassert>
#include <initializer_list>

extern "C" void arboresce_test_status(arboresce_status code);

int main() {
    static_assert(noexcept(arboresce::name()));
    static_assert(noexcept(arboresce::print_name()));
    for (arboresce_status code :
         {ARBORESCE_INVALID_ARGUMENT, ARBORESCE_PANIC, 99}) {
        arboresce_test_status(code);
        const auto result = arboresce::name();
        assert(!result);
        assert(result.value.empty());
        assert(static_cast<std::uint32_t>(result.code) == code);
        assert(static_cast<std::uint32_t>(arboresce::print_name()) == code);
    }
    arboresce_test_status(ARBORESCE_OK);
    const auto empty = arboresce::name();
    assert(empty);
    assert(empty.value.empty());
    assert(arboresce::print_name() == arboresce::status::ok);
    return 0;
}
