# Arboresce C++ SDK

C++ SDK for Arboresce.

Build locally with `make build-cpp`; use
`find_package(ArboresceCpp CONFIG REQUIRED)` and `Arboresce::cpp` or
`Arboresce::cpp_static`. The development prefix is `build/native/install`.
See [Developers](../../DEVELOPERS.md) for ownership, status, and qualification contracts.

```cpp
#include <arboresce/arboresce.hpp>
#include <iostream>

int main() {
    const auto result = arboresce::name();
    if (!result) {
        return 1;
    }
    std::cout << result.value << '\n';
    return arboresce::print_name() == arboresce::status::ok ? 0 : 1;
}
```
