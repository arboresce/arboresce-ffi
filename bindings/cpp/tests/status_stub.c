#include <arboresce/arboresce.h>

static arboresce_status selected;

void arboresce_test_status(arboresce_status code) { selected = code; }

uint32_t arboresce_v1_abi_version(void) { return ARBORESCE_ABI_VERSION; }

arboresce_status arboresce_v1_name(arboresce_string_view *output) {
    output->data = selected == ARBORESCE_OK ? NULL : "ignored";
    output->len = selected == ARBORESCE_OK ? 0 : 7;
    return selected;
}

arboresce_status arboresce_v1_print_name(void) { return selected; }
