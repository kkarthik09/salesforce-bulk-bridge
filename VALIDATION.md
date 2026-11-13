# Local validation

2026-11-13. Command: `python3 -m unittest -v`. Exit: 0

```text
test_ambiguous_creation_not_retried (test_bridge.Tests.test_ambiguous_creation_not_retried) ... ok
test_bad_csv (test_bridge.Tests.test_bad_csv) ... ok
test_changed_input (test_bridge.Tests.test_changed_input) ... ok
test_destination_binding (test_bridge.Tests.test_destination_binding) ... ok
test_lifecycle_and_replay (test_bridge.Tests.test_lifecycle_and_replay) ... ok
test_origins (test_bridge.Tests.test_origins) ... ok
test_poll_resume (test_bridge.Tests.test_poll_resume) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.018s

OK
```

No live org, mobile device, customer adoption or production load validation is implied.
