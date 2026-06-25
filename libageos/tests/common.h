#pragma once

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define AGEOS_TEST_FAIL(...)          \
    do {                              \
        fprintf(stderr, __VA_ARGS__); \
        fputc('\n', stderr);          \
        return 1;                     \
    } while (0)

#define AGEOS_TEST_EXPECT(condition, ...) \
    do {                                  \
        if (!(condition)) {               \
            AGEOS_TEST_FAIL(__VA_ARGS__); \
        }                                 \
    } while (0)

#define AGEOS_TEST_EXPECT_INT(actual, expected, label)                                                         \
    do {                                                                                                       \
        int ageos_test_actual_ = (actual);                                                                     \
        int ageos_test_expected_ = (expected);                                                                 \
        if (ageos_test_actual_ != ageos_test_expected_) {                                                      \
            AGEOS_TEST_FAIL("%s mismatch: got=%d want=%d", (label), ageos_test_actual_, ageos_test_expected_); \
        }                                                                                                      \
    } while (0)

#define AGEOS_TEST_EXPECT_STR(actual, expected, label)               \
    do {                                                             \
        const char *ageos_test_actual_ = (actual);                   \
        const char *ageos_test_expected_ = (expected);               \
        if (strcmp(ageos_test_actual_, ageos_test_expected_) != 0) { \
            AGEOS_TEST_FAIL(                                         \
                "%s mismatch: got=%s want=%s",                       \
                (label),                                             \
                ageos_test_actual_,                                  \
                ageos_test_expected_);                               \
        }                                                            \
    } while (0)

#define AGEOS_TEST_EXPECT_CONTAINS(haystack, needle, label)             \
    do {                                                                \
        const char *ageos_test_haystack_ = (haystack);                  \
        const char *ageos_test_needle_ = (needle);                      \
        if (strstr(ageos_test_haystack_, ageos_test_needle_) == NULL) { \
            AGEOS_TEST_FAIL(                                            \
                "%s missing substring: needle=%s haystack=%s",          \
                (label),                                                \
                ageos_test_needle_,                                     \
                ageos_test_haystack_);                                  \
        }                                                               \
    } while (0)

static __attribute__((unused)) int ageos_test_make_tempdir(char *template_path) {
    return mkdtemp(template_path) == NULL ? 1 : 0;
}

static __attribute__((unused)) int ageos_test_read_file(const char *path, char *buffer, size_t buffer_size) {
    FILE *handle = fopen(path, "r");
    if (handle == NULL || buffer == NULL || buffer_size == 0) {
        if (handle != NULL) {
            fclose(handle);
        }
        return 1;
    }
    size_t count = fread(buffer, 1, buffer_size - 1, handle);
    fclose(handle);
    buffer[count] = '\0';
    return 0;
}

static __attribute__((unused)) int ageos_test_file_contains(const char *path, const char *needle) {
    char buffer[8192];
    return ageos_test_read_file(path, buffer, sizeof(buffer)) == 0 && strstr(buffer, needle) != NULL;
}

static __attribute__((unused)) int ageos_test_is_dir(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static __attribute__((unused)) int ageos_test_is_file(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 && S_ISREG(st.st_mode);
}
