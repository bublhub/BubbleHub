#define _GNU_SOURCE

#include "ageos/overfs.h"
#include "common.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>

typedef struct {
    char source[PATH_MAX];
    char target[PATH_MAX];
    char filesystem[64];
    unsigned long flags;
    char data[256];
} ageos_mount_call;

static ageos_mount_call g_mount_calls[16];
static int g_mount_call_count = 0;

static void reset_mount_calls(void) {
    memset(g_mount_calls, 0, sizeof(g_mount_calls));
    g_mount_call_count = 0;
}

int ageos_test_mount(const char *source, const char *target, const char *filesystemtype, unsigned long mountflags, const void *data) {
    if (g_mount_call_count >= (int)(sizeof(g_mount_calls) / sizeof(g_mount_calls[0]))) {
        errno = ENOMEM;
        return -1;
    }
    ageos_mount_call *call = &g_mount_calls[g_mount_call_count++];
    snprintf(call->source, sizeof(call->source), "%s", source != NULL ? source : "");
    snprintf(call->target, sizeof(call->target), "%s", target != NULL ? target : "");
    snprintf(call->filesystem, sizeof(call->filesystem), "%s", filesystemtype != NULL ? filesystemtype : "");
    snprintf(call->data, sizeof(call->data), "%s", data != NULL ? (const char *)data : "");
    call->flags = mountflags;
    return 0;
}

static int test_rootfs_and_join(void) {
    ageos_sandbox_config cfg = {0};
    AGEOS_TEST_EXPECT(!ageos_overfs_rootfs_enabled(&cfg), "expected empty rootfs to be disabled");
    cfg.rootfs_dir = "/rootfs";
    AGEOS_TEST_EXPECT(ageos_overfs_rootfs_enabled(&cfg), "expected configured rootfs to be enabled");

    char buffer[128];
    AGEOS_TEST_EXPECT_INT(ageos_overfs_join_mount_path(NULL, "/etc", buffer, sizeof(buffer)), 0, "join without root");
    AGEOS_TEST_EXPECT_STR(buffer, "/etc", "join without root");
    AGEOS_TEST_EXPECT_INT(ageos_overfs_join_mount_path("/sandbox", "/etc", buffer, sizeof(buffer)), 0, "join with root");
    AGEOS_TEST_EXPECT_STR(buffer, "/sandbox/etc", "join with root");
    AGEOS_TEST_EXPECT_INT(ageos_overfs_join_mount_path("/sandbox", "etc", buffer, sizeof(buffer)), -EINVAL, "join relative path");

    char small[4];
    AGEOS_TEST_EXPECT_INT(ageos_overfs_join_mount_path("/sandbox", "/toolong", small, sizeof(small)), -ENAMETOOLONG, "join short buffer");
    return 0;
}

static int test_path_creation(void) {
    char temp_dir[] = "/tmp/ageos-overfs-test-XXXXXX";
    AGEOS_TEST_EXPECT_INT(ageos_test_make_tempdir(temp_dir), 0, "create overfs tempdir");

    char nested_dir[PATH_MAX];
    snprintf(nested_dir, sizeof(nested_dir), "%s/a/b/c", temp_dir);
    AGEOS_TEST_EXPECT_INT(ageos_overfs_mkdir_p(nested_dir, 0755), 0, "mkdir_p nested");
    AGEOS_TEST_EXPECT(ageos_test_is_dir(nested_dir), "expected directory %s to exist", nested_dir);

    char file_path[PATH_MAX];
    snprintf(file_path, sizeof(file_path), "%s/files/state.json", temp_dir);
    AGEOS_TEST_EXPECT_INT(ageos_overfs_ensure_file(file_path, 0644), 0, "ensure_file create");
    AGEOS_TEST_EXPECT_INT(ageos_overfs_ensure_file(file_path, 0644), 0, "ensure_file idempotent");
    AGEOS_TEST_EXPECT(ageos_test_is_file(file_path), "expected file %s to exist", file_path);
    return 0;
}

static int test_bind_helpers(void) {
    char temp_dir[] = "/tmp/ageos-overfs-bind-XXXXXX";
    AGEOS_TEST_EXPECT_INT(ageos_test_make_tempdir(temp_dir), 0, "create bind tempdir");

    char source_file[PATH_MAX];
    char source_dir[PATH_MAX];
    char target_file[PATH_MAX];
    char target_dir[PATH_MAX];
    snprintf(source_file, sizeof(source_file), "%s/source.txt", temp_dir);
    snprintf(source_dir, sizeof(source_dir), "%s/source-dir", temp_dir);
    snprintf(target_file, sizeof(target_file), "%s/target.txt", temp_dir);
    snprintf(target_dir, sizeof(target_dir), "%s/target-dir", temp_dir);

    FILE *handle = fopen(source_file, "w");
    AGEOS_TEST_EXPECT(handle != NULL, "failed to create %s", source_file);
    fputs("ok", handle);
    fclose(handle);
    AGEOS_TEST_EXPECT(mkdir(source_dir, 0755) == 0, "failed to create %s", source_dir);

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_file_readonly(source_file, target_file), 0, "bind file readonly");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 2, "bind file readonly calls");
    AGEOS_TEST_EXPECT_STR(g_mount_calls[0].source, source_file, "bind file readonly source");
    AGEOS_TEST_EXPECT_STR(g_mount_calls[0].target, target_file, "bind file readonly target");
    AGEOS_TEST_EXPECT(g_mount_calls[1].flags == (MS_BIND | MS_REMOUNT | MS_RDONLY), "unexpected readonly remount flags");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_file_readwrite(source_file, target_file), 0, "bind file readwrite");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 1, "bind file readwrite calls");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_dir(source_dir, target_dir), 0, "bind dir");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 1, "bind dir calls");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_optional_dir_readonly("/missing", target_dir), 0, "optional dir missing");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 0, "optional dir missing calls");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_optional_dir_readonly(source_dir, target_dir), 0, "optional dir readonly");
    AGEOS_TEST_EXPECT(ageos_test_is_dir(target_dir), "expected target dir %s to exist", target_dir);
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 2, "optional dir readonly calls");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_optional_file_readonly("/missing", target_file), 0, "optional file missing");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 0, "optional file missing calls");

    unlink(target_file);
    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_bind_optional_file_readonly(source_file, target_file), 0, "optional file readonly");
    AGEOS_TEST_EXPECT(ageos_test_is_file(target_file), "expected target file %s to exist", target_file);
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 2, "optional file readonly calls");

    reset_mount_calls();
    AGEOS_TEST_EXPECT_INT(ageos_overfs_mount_tmpfs_at(target_dir, "mode=1777,size=1m"), 0, "mount tmpfs");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 1, "mount tmpfs calls");
    AGEOS_TEST_EXPECT_STR(g_mount_calls[0].source, "tmpfs", "tmpfs source");
    AGEOS_TEST_EXPECT_STR(g_mount_calls[0].filesystem, "tmpfs", "tmpfs filesystem");
    return 0;
}

static int test_setup_mounts(void) {
    char temp_dir[] = "/tmp/ageos-overfs-setup-XXXXXX";
    AGEOS_TEST_EXPECT_INT(ageos_test_make_tempdir(temp_dir), 0, "create setup tempdir");

    reset_mount_calls();
    ageos_sandbox_config cfg = {0};
    AGEOS_TEST_EXPECT_INT(ageos_overfs_setup_mounts(temp_dir, &cfg), 0, "setup mounts without rootfs");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 1, "setup mounts without rootfs calls");
    AGEOS_TEST_EXPECT(g_mount_calls[0].flags == (MS_REC | MS_PRIVATE), "unexpected namespace flags");

    reset_mount_calls();
    cfg.rootfs_dir = "/rootfs";
    AGEOS_TEST_EXPECT_INT(ageos_overfs_setup_mounts(temp_dir, &cfg), -EINVAL, "setup mounts missing overlay dirs");
    AGEOS_TEST_EXPECT_INT(g_mount_call_count, 1, "setup mounts rootfs calls");
    return 0;
}

int main(void) {
    if (test_rootfs_and_join() != 0) {
        return 1;
    }
    if (test_path_creation() != 0) {
        return 1;
    }
    if (test_bind_helpers() != 0) {
        return 1;
    }
    if (test_setup_mounts() != 0) {
        return 1;
    }
    return 0;
}
