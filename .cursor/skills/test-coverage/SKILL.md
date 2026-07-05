---
name: test-coverage
description: Enforce thorough test coverage for BubbleHub changes. Use when fixing Codecov failures, patch coverage, missing coverage lines, C unit tests, Meson tests, hard-to-reach error paths, mocks, or mocked POSIX/syscall behavior.
---

# Test Coverage

## Core Rule

"test coverage, always test every line, use mocks, mock syscalls...."

When changing this repository, treat uncovered changed lines as unfinished work. If Codecov reports missing patch coverage, add focused tests until every meaningful new branch and return path is exercised.

## Workflow

1. Start from the coverage report:
   - Identify the exact changed file and missing lines.
   - Map each missing line to the behavior or error path it represents.
   - Prefer a focused unit test over broad integration coverage when the missing line is local logic.

2. Test every changed path:
   - Cover success paths, idempotent paths, and each meaningful failure return.
   - Do not leave defensive branches uncovered just because they are inconvenient.
   - If a branch depends on rare I/O, filesystem, process, network, or kernel behavior, use a mock instead of relying on timing or host state.

3. For C syscall failures, mock at the test binary boundary:
   - Keep production C calling normal POSIX/libc functions.
   - Do not add `#ifdef TEST`, global fault enums, or production-only test hooks.
   - For GCC/Clang Meson tests, prefer linker wrapping with `-Wl,--wrap=<symbol>`.
   - Wrap the actual emitted symbols for the toolchain. For example, `open()` may compile to `open64`, so tests may need both `--wrap=open` and `--wrap=open64`.

4. Write mocks locally in the test file:
   - Use small flags such as `g_fail_open`, `g_fail_read`, or `g_fail_write`.
   - Set `errno` to the expected failure, return the libc failure value, and assert the production code returns the expected negative errno.
   - Reset mock flags immediately after each assertion.
   - Use the real function via `__real_<symbol>` for all non-failing cases.

Example:

```c
int __real_open64(const char *path, int flags, ...);
static int g_fail_append_open = 0;

int __wrap_open64(const char *path, int flags, ...) {
    if (g_fail_append_open && (flags & O_APPEND)) {
        errno = EACCES;
        return -1;
    }
    if (flags & O_CREAT) {
        va_list ap;
        va_start(ap, flags);
        mode_t mode = va_arg(ap, mode_t);
        va_end(ap);
        return __real_open64(path, flags, mode);
    }
    return __real_open64(path, flags);
}
```

Meson pattern:

```meson
executable(
  'bubble-sandbox-internal-test',
  'sandbox_internal_test.c',
  link_args: [
    '-Wl,--wrap=open',
    '-Wl,--wrap=open64',
  ],
)
```

## Verification

Run the narrow tests first, then broader checks when needed:

```bash
meson test -C libbubble/build <test-name> --print-errorlogs
```

If coverage is the blocker, prefer reproducing the coverage target used by CI when the local build supports it:

```bash
ninja -C libbubble/build coverage-xml
```

Report which missing lines were covered and which mocks were added.
