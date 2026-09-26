#include <arboresce/arboresce.h>
#include <assert.h>
#include <pthread.h>
#include <string.h>

static void *exercise(void *argument) {
    (void)argument;
    const char *previous = NULL;
    for (int i = 0; i < 1000; ++i) {
        arboresce_string_view name = {NULL, 0};
        assert(arboresce_v1_name(&name) == ARBORESCE_OK);
        assert(name.len == 9);
        assert(memcmp(name.data, "Arboresce", name.len) == 0);
        assert(previous == NULL || previous == name.data);
        previous = name.data;
    }
    return NULL;
}

int main(void) {
    assert(arboresce_v1_abi_version() == ARBORESCE_ABI_VERSION);
    assert(arboresce_v1_name(NULL) == ARBORESCE_INVALID_ARGUMENT);
    pthread_t threads[8];
    for (int i = 0; i < 8; ++i) {
        assert(pthread_create(&threads[i], NULL, exercise, NULL) == 0);
    }
    for (int i = 0; i < 8; ++i) {
        assert(pthread_join(threads[i], NULL) == 0);
    }
    return 0;
}
