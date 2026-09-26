#include <arboresce/arboresce.hpp>

int main() {
    const auto result = arboresce::name();
    if (!result || result.value != "Arboresce") {
        return 1;
    }
    return arboresce::print_name() == arboresce::status::ok ? 0 : 1;
}
