#include "ageos/log.h"
#include "common.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static int test_log_file_output(void) {
    char temp_dir[] = "/tmp/ageos-log-test-XXXXXX";
    AGEOS_TEST_EXPECT_INT(ageos_test_make_tempdir(temp_dir), 0, "create log tempdir");

    char log_path[PATH_MAX];
    snprintf(log_path, sizeof(log_path), "%s/native.log", temp_dir);

    unsetenv("AGEOS_SANDBOX");
    ageos_log_set_level("debug");
    ageos_log_set_file(log_path);
    ageos_log_write(AGEOS_LOG_LEVEL_DEBUG, "/tmp/scheduler.c", 625, "evicted model", "name=%s", "test-model");

    AGEOS_TEST_EXPECT(
        ageos_test_file_contains(log_path, "DEBUG scheduler.c:625 evicted model:name=test-model"),
        "expected debug log to be written to %s",
        log_path);
    return 0;
}

static int test_sandbox_log_path_policy(void) {
    char temp_dir[] = "/tmp/ageos-log-sandbox-XXXXXX";
    AGEOS_TEST_EXPECT_INT(ageos_test_make_tempdir(temp_dir), 0, "create sandbox log tempdir");

    char agent_home[PATH_MAX];
    char workspace[PATH_MAX];
    char sandbox_tmp[PATH_MAX];
    snprintf(agent_home, sizeof(agent_home), "%s/home", temp_dir);
    snprintf(workspace, sizeof(workspace), "%s/workspace", temp_dir);
    snprintf(sandbox_tmp, sizeof(sandbox_tmp), "%s/tmp", temp_dir);
    AGEOS_TEST_EXPECT(mkdir(agent_home, 0755) == 0, "failed to create %s", agent_home);
    AGEOS_TEST_EXPECT(mkdir(workspace, 0755) == 0, "failed to create %s", workspace);
    AGEOS_TEST_EXPECT(mkdir(sandbox_tmp, 0755) == 0, "failed to create %s", sandbox_tmp);

    setenv("AGEOS_SANDBOX", "1", 1);
    setenv("AGEOS_AGENT_HOME", agent_home, 1);
    setenv("AGEOS_WORKSPACE", workspace, 1);
    setenv("TMPDIR", sandbox_tmp, 1);
    setenv("HOME", agent_home, 1);

    char blocked_path[PATH_MAX];
    snprintf(blocked_path, sizeof(blocked_path), "/var/tmp/ageos-blocked-%ld.log", (long)getpid());
    unlink(blocked_path);

    ageos_log_set_level("info");
    ageos_log_set_file(blocked_path);
    ageos_log_write(AGEOS_LOG_LEVEL_INFO, "/tmp/log.c", 42, "blocked host log", NULL);
    AGEOS_TEST_EXPECT(access(blocked_path, F_OK) != 0, "sandbox unexpectedly allowed host log file %s", blocked_path);

    char allowed_path[PATH_MAX];
    size_t workspace_len = strlen(workspace);
    AGEOS_TEST_EXPECT(
        workspace_len + sizeof("/allowed.log") <= sizeof(allowed_path),
        "workspace path too long: %s",
        workspace);
    memcpy(allowed_path, workspace, workspace_len);
    memcpy(allowed_path + workspace_len, "/allowed.log", sizeof("/allowed.log"));
    ageos_log_set_file(allowed_path);
    ageos_log_write(AGEOS_LOG_LEVEL_INFO, "/tmp/log.c", 84, "workspace log", NULL);
    AGEOS_TEST_EXPECT(
        ageos_test_file_contains(allowed_path, "INFO log.c:84 workspace log"),
        "expected sandbox log file to be written to %s",
        allowed_path);
    return 0;
}

int main(void) {
    if (test_log_file_output() != 0) {
        return 1;
    }
    if (test_sandbox_log_path_policy() != 0) {
        return 1;
    }
    return 0;
}
