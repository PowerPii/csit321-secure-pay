# Acceptance tests for the non-functional requirements

Each test here checks one acceptance criterion from URS Section 4.4 (Tables 4.4.1.1 to
4.4.9.1) at the numbers the URS states (20 records, 50 webhooks, 100 retries, 150 requests and
so on). The test name starts with the requirement: `test_nfr_con_01_...` checks NFR-CON-01.

They run with the other gateway tests (`pytest` in `gateway/`) and in CI on every push. The
test report (`docs/test-report/`) maps every requirement to these tests, to older unit tests
that cover it too, and to the manual checks that need the live server.

Requirements that need the live server, a browser or people (TLS scan, load test, kill test,
accessibility, walkthroughs) are not here; see `docs/test-report/MANUAL-TESTS.md`.
