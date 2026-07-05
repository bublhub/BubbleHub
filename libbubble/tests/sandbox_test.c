#include "bubblehub/sandbox.h"

#include "test_common.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int test_null_config(void) {
    TEST_CHECK_EQ(bubblehub_sandbox_run(NULL), -EINVAL);
    return 0;
}

static int test_missing_binary(void) {
    char *argv[] = {NULL};
    bubblehub_sandbox_config cfg = {
        .binary = NULL,
        .argv = argv,
        .workdir = "/tmp",
    };
    TEST_CHECK_EQ(bubblehub_sandbox_run(&cfg), -EINVAL);
    return 0;
}

static int test_missing_argv(void) {
    bubblehub_sandbox_config cfg = {
        .binary = "/bin/true",
        .argv = NULL,
        .workdir = "/tmp",
    };
    TEST_CHECK_EQ(bubblehub_sandbox_run(&cfg), -EINVAL);
    return 0;
}

static int test_missing_workdir(void) {
    char *argv[] = {"/bin/true", NULL};
    bubblehub_sandbox_config cfg = {
        .binary = "/bin/true",
        .argv = argv,
        .workdir = NULL,
    };
    TEST_CHECK_EQ(bubblehub_sandbox_run(&cfg), -EINVAL);
    return 0;
}

#ifdef __linux__
static int read_file(const char *path, char *buffer, size_t buffer_size) {
    FILE *file = fopen(path, "r");
    if (file == NULL) {
        return -errno;
    }
    size_t read_count = fread(buffer, 1, buffer_size - 1, file);
    if (ferror(file)) {
        int err = errno;
        fclose(file);
        return -err;
    }
    buffer[read_count] = '\0';
    fclose(file);
    return 0;
}

static int count_occurrences(const char *haystack, const char *needle) {
    int count = 0;
    size_t needle_len = strlen(needle);
    const char *cursor = haystack;
    while ((cursor = strstr(cursor, needle)) != NULL) {
        count++;
        cursor += needle_len;
    }
    return count;
}

static int test_sandbox_home_profiles_restore_prompt_once(void) {
    char *root_dir = test_mkdtemp_copy("bubblehub-sandbox-profile-test");
    TEST_CHECK(root_dir != NULL);

    char *argv[] = {
        "/bin/sh",
        "-c",
        "test -n \"$BUBBLEHUB_PS1\" && "
        "test \"$PS1\" = \"$BUBBLEHUB_PS1\" && "
        "grep -q 'BubbleHub prompt restore' \"$HOME/.bashrc\"",
        NULL,
    };
    bubblehub_sandbox_config cfg = {
        .binary = "/bin/sh",
        .argv = argv,
        .resource_niceness = 0,
        .memory_max = 2ULL * 1024ULL * 1024ULL * 1024ULL,
        .cpu_percent = 0,
        .workdir = root_dir,
        .root_dir = root_dir,
        .agent_id = "agt-profile-test",
        .isolate_network = 0,
    };

    int first = bubblehub_sandbox_run(&cfg);
    if (first == 126) {
        fprintf(stderr, "SKIP sandbox execution unavailable in this environment\n");
        free(root_dir);
        return 0;
    }
    TEST_CHECK_EQ(first, 0);
    TEST_CHECK_EQ(bubblehub_sandbox_run(&cfg), 0);

    char bashrc_path[512];
    int written = snprintf(
        bashrc_path,
        sizeof(bashrc_path),
        "%s/.bubblehub/agents/agt-profile-test/home/.bashrc",
        root_dir);
    TEST_CHECK(written > 0 && (size_t)written < sizeof(bashrc_path));

    char bashrc[4096];
    TEST_CHECK_EQ(read_file(bashrc_path, bashrc, sizeof(bashrc)), 0);
    TEST_CHECK_EQ(count_occurrences(bashrc, "BubbleHub prompt restore"), 1);

    free(root_dir);
    return 0;
}
#endif

#ifndef __linux__
static int test_unsupported_platform(void) {
    char *argv[] = {"/bin/true", NULL};
    bubblehub_sandbox_config cfg = {
        .binary = "/bin/true",
        .argv = argv,
        .workdir = "/tmp",
    };
    TEST_CHECK_EQ(bubblehub_sandbox_run(&cfg), -ENOTSUP);
    return 0;
}
#endif

int main(void) {
    int rc = 0;
    rc |= test_null_config();
    rc |= test_missing_binary();
    rc |= test_missing_argv();
    rc |= test_missing_workdir();
#ifdef __linux__
    rc |= test_sandbox_home_profiles_restore_prompt_once();
#endif
#ifndef __linux__
    rc |= test_unsupported_platform();
#endif
    return rc;
}
