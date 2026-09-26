#include <arboresce/arboresce.h>
#include <string.h>

int main(void) {
    arboresce_string_view name = {NULL, 0};
    if (arboresce_v1_abi_version() != ARBORESCE_ABI_VERSION ||
        arboresce_v1_name(&name) != ARBORESCE_OK || name.len != 9 ||
        memcmp(name.data, "Arboresce", name.len) != 0) {
        return 1;
    }
    return arboresce_v1_print_name() == ARBORESCE_OK ? 0 : 1;
}
