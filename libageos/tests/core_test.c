#include "ageos/hw.h"
#include "ageos/limits.h"
#include "ageos/sandbox.h"
#include "common.h"

#include <errno.h>

static int test_hw_queries(void) {
    AGEOS_TEST_EXPECT(ageos_hw_total_ram_bytes() > 0, "expected total RAM to be detected");
    (void)ageos_hw_vram_bytes();
    (void)ageos_hw_free_vram_bytes();
    return 0;
}

static int test_limits_validation(void) {
    ageos_sandbox_config cfg = {0};
    AGEOS_TEST_EXPECT_INT(ageos_apply_cgroup_limits(NULL), -EINVAL, "limits null cfg");
    AGEOS_TEST_EXPECT_INT(ageos_apply_cgroup_limits(&cfg), 0, "limits empty cfg");
    return 0;
}

static int test_sandbox_validation(void) {
    AGEOS_TEST_EXPECT_INT(ageos_sandbox_run(NULL), -EINVAL, "sandbox null cfg");
    return 0;
}

int main(void) {
    if (test_hw_queries() != 0) {
        return 1;
    }
    if (test_limits_validation() != 0) {
        return 1;
    }
    if (test_sandbox_validation() != 0) {
        return 1;
    }
    return 0;
}
