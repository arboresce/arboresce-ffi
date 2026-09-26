#include <arboresce/arboresce.hpp>
#include <cassert>
#include <thread>
#include <vector>

static_assert(noexcept(arboresce::name()));
static_assert(noexcept(arboresce::print_name()));

int main() {
    std::vector<std::thread> workers;
    for (int i = 0; i < 8; ++i) {
        workers.emplace_back([] {
            for (int j = 0; j < 1000; ++j) {
                const auto result = arboresce::name();
                assert(result);
                assert(result.value == "Arboresce");
            }
        });
    }
    for (auto &worker : workers) {
        worker.join();
    }
    return arboresce::print_name() == arboresce::status::ok ? 0 : 1;
}
