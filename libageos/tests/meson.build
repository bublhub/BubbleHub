http_proxy_test = executable(
  'ageos-http-proxy-test',
  ['http_proxy_test.c'],
  include_directories: include_dir,
  link_with: libageos,
  install: false,
)
test('http-proxy', http_proxy_test)

core_test = executable(
  'ageos-core-test',
  ['core_test.c'],
  include_directories: include_dir,
  link_with: libageos,
  install: false,
)
test('core', core_test)

log_test = executable(
  'ageos-log-test',
  ['log_test.c'],
  include_directories: include_dir,
  link_with: libageos,
  install: false,
)
test('log', log_test)

overfs_test = executable(
  'ageos-overfs-test',
  ['overfs_test.c', '../overfs.c', '../log.c'],
  include_directories: include_dir,
  c_args: ['-Dmount=ageos_test_mount'],
  install: false,
)
test('overfs', overfs_test)

scheduler_test = executable(
  'ageos-scheduler-test',
  ['scheduler_test.c'],
  include_directories: include_dir,
  link_with: libageos,
  install: false,
)
test('scheduler', scheduler_test)
