#include "ageos/scheduler.h"
#include "common.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int setup_scheduler_state(char *state_path, size_t state_path_size) {
    char temp_dir[] = "/tmp/ageos-scheduler-test-XXXXXX";
    if (ageos_test_make_tempdir(temp_dir) != 0) {
        return 1;
    }
    snprintf(state_path, state_path_size, "%s/scheduler.state", temp_dir);
    return setenv("AGEOS_SCHEDULER_STATE", state_path, 1) == 0 ? 0 : 1;
}

static int expect_snapshot_contains(const char *needle, const char *label) {
    char *snapshot = ageos_scheduler_snapshot_json();
    AGEOS_TEST_EXPECT(snapshot != NULL, "failed to create scheduler snapshot");
    AGEOS_TEST_EXPECT_CONTAINS(snapshot, needle, label);
    ageos_scheduler_free_string(snapshot);
    return 0;
}

static int expect_snapshot_lacks(const char *needle, const char *label) {
    char *snapshot = ageos_scheduler_snapshot_json();
    AGEOS_TEST_EXPECT(snapshot != NULL, "failed to create scheduler snapshot");
    AGEOS_TEST_EXPECT(strstr(snapshot, needle) == NULL, "%s unexpectedly found %s", label, needle);
    ageos_scheduler_free_string(snapshot);
    return 0;
}

static int test_invalid_inputs(void) {
    char state[64];
    char reason[256];
    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_admit_model_job("default-instruct", "tiny", 0, 0.0, 0.0, NULL, state, sizeof(state), reason, sizeof(reason)),
        -1,
        "scheduler admit invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_register_agent(NULL, 1, "/bin/agent", 0, "default-instruct"), -1, "register invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_deregister_agent(NULL), -1, "deregister invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_mark_model_loaded(NULL, "default-instruct", "llama", 1.0, 0.0, 1, 1), -1, "mark loaded invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_mark_model_unloaded(NULL), -1, "mark unloaded invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_evict_model(NULL), -1, "evict invalid");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_add_queue_item(NULL, "model_load", "default-instruct", "tiny", 0, "reason"), -1, "queue invalid");
    return 0;
}

static int test_scheduler_lifecycle(void) {
    char state_path[PATH_MAX];
    AGEOS_TEST_EXPECT_INT(setup_scheduler_state(state_path, sizeof(state_path)), 0, "setup scheduler state");

    AGEOS_TEST_EXPECT_INT(ageos_scheduler_configure_limits(10.0, 0.0), 0, "configure limits");
    if (expect_snapshot_contains("\"limits\":{\"ram_bytes\":10737418240", "configured limits") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(ageos_scheduler_register_agent("agent-1", 12345, "/bin/agent", 0, "default-instruct"), 0, "register agent");
    if (expect_snapshot_contains("\"binary\":\"/bin/agent\"", "registered agent") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_mark_model_loaded("loaded", "default-instruct", "llama", 2.0, 0.0, 999999, 51000),
        0,
        "mark model loaded");
    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_mark_model_loaded("loaded", "default-instruct", "llama", 2.0, 0.0, 999999, 51000),
        0,
        "mark model loaded second");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_mark_model_unloaded("loaded"), 0, "mark model unloaded");
    if (expect_snapshot_contains("\"name\":\"loaded\"", "loaded model present") != 0) {
        return 1;
    }
    if (expect_snapshot_contains("\"refcount\":1", "loaded model refcount") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(ageos_scheduler_evict_model("loaded"), 0, "evict model");
    if (expect_snapshot_lacks("\"name\":\"loaded\"", "evicted model absent") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_mark_model_loaded("old", "default-instruct", "llama", 6.0, 0.0, 999998, 51001),
        0,
        "mark idle model loaded");
    AGEOS_TEST_EXPECT_INT(ageos_scheduler_mark_model_unloaded("old"), 0, "mark idle model unloaded");

    int allowed = 1;
    char pressure[64];
    char reason[256];
    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_admit_model_job("default-instruct", "large", 10, 8.5, 0.0, &allowed, pressure, sizeof(pressure), reason, sizeof(reason)),
        0,
        "admit low ram model");
    AGEOS_TEST_EXPECT(!allowed, "expected large background model to queue");
    AGEOS_TEST_EXPECT_STR(pressure, "low", "memory pressure");
    AGEOS_TEST_EXPECT_CONTAINS(reason, "RAM low", "low memory reason");
    if (expect_snapshot_contains("\"model_name\":\"large\"", "queued model") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_admit_model_job("default-instruct", "new", 0, 6.0, 0.0, &allowed, pressure, sizeof(pressure), reason, sizeof(reason)),
        0,
        "admit model after eviction");
    AGEOS_TEST_EXPECT(allowed, "expected foreground model to be admitted");
    if (expect_snapshot_lacks("\"name\":\"old\"", "idle model evicted") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(
        ageos_scheduler_add_queue_item("job-manual", "model_load", "default-instruct", "manual", 5, "manual reason"),
        0,
        "manual queue item");
    if (expect_snapshot_contains("\"job_id\":\"job-manual\"", "manual queue item") != 0) {
        return 1;
    }

    AGEOS_TEST_EXPECT_INT(ageos_scheduler_deregister_agent("agent-1"), 0, "deregister agent");
    if (expect_snapshot_lacks("\"binary\":\"/bin/agent\"", "agent removed") != 0) {
        return 1;
    }

    char *error = ageos_inference_chat_json(NULL);
    AGEOS_TEST_EXPECT(error != NULL, "expected inference error json");
    AGEOS_TEST_EXPECT_CONTAINS(error, "invalid native inference request", "inference error");
    ageos_scheduler_free_string(error);
    return 0;
}

int main(void) {
    if (test_invalid_inputs() != 0) {
        return 1;
    }
    if (test_scheduler_lifecycle() != 0) {
        return 1;
    }
    return 0;
}
