## What

<!-- One or two sentences. -->

## Requirements and demo story

<!-- e.g. CP FR 9, TL FR 6; moves S1 forward -->

## How I tested it

<!-- Commands run, new tests added. -->

## Checklist

- [ ] No card data or secrets outside the vault (logs, audit, outbox, features, fixtures)
- [ ] Queries scoped to the caller's merchant or role, with a negative test
- [ ] State changes go through `check_transition` and write the outbox in the same transaction
- [ ] Business numbers read from `GATEWAY_RULES`
