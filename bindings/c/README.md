# Arboresce C SDK

C SDK for Arboresce.
Build and install locally with `make install-c`; use
`find_package(Arboresce CONFIG REQUIRED)` and `Arboresce::c_shared` or
`Arboresce::c_static`. `Arboresce::c` selects shared linkage.
The development prefix is `build/native/install`. See [Developers](../../DEVELOPERS.md)
for the borrowed-memory safety contract, status meanings, and qualification limits.

```c
#include <arboresce/arboresce.h>
#include <stdio.h>

int main(void) {
    arboresce_string_view name = {NULL, 0};
    if (arboresce_v1_name(&name) != ARBORESCE_OK) {
        return 1;
    }
    fwrite(name.data, 1, name.len, stdout);
    putchar('\n');
    return arboresce_v1_print_name() == ARBORESCE_OK ? 0 : 1;
}
```
