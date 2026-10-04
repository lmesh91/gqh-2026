# Milestone 1 — current design version 3

Start with [SIMPLIFICATION.md](SIMPLIFICATION.md): the prefunded trading-account idea, worked $10,000 example, tradeoffs and reading guide.

[DESIGN.md](DESIGN.md) is the current rulebook. Clients fund accounts at planetary exchanges; orders, partial fills, cancellation and settlement use local authoritative balances. Funding and home withdrawals use explicitly backed transfers. It includes the brief's requirements, account closure, replay/recovery, later-price contract, quotas, storage and scenario definitions.

[IMPLEMENTATION.md](IMPLEMENTATION.md) gives the v3 migration and evidence checklist for the agent doing Milestones 2–3. That agent's files are not modified here, and its existing results are not assumed to implement this revision.

## Reproduce current bounded financial evidence

From the repository root, using Python 3:

```sh
python3 milestone1/checks_v3.py
```

This runs 23 financial tests (including six serial permutations of a fill/cancel/withdrawal race), writes the $10k account example, checks record packing and emits v3 provenance. It requires no network and does not overwrite historical v2 evidence or Milestone 2 files.

The reference ledger is `prefunded_accounts.py`. It is a bounded model of funding, local order holds, partial-fill ledger effects and withdrawals, assuming atomic durable operations and authenticated honest operators. It does not implement the full order matcher, account-close lifecycle, derivative engine, durable storage, compaction, wire encoding or transport.

See [results/README.md](results/README.md) for evidence classification. V3 does **not** claim new packet-trace timings; packet savings in DESIGN are structural calculations. The v2 Earth–Mars timing is historical.

## Shared geometry and history

`model.py` and existing geometry outputs remain reusable. To rerun its short checks use `python3 milestone1/model.py`; add `--scan` for the expensive 200-year hourly screen (NumPy required). These write shared geometry outputs, so coordinate with the Milestone 2 agent before rerunning during its work.

`archive/*-v2.md` preserves the previous documents; `archive/*-v1.md` preserves the original architecture. `direct_settlement.py`, `test_direct_settlement.py`, `trace_v2.py` and `checks_v2.py` are historical v2 code, not current account-model validation. `verify.py`, `checks.py` and `third_site_example.py` reproduce v1 material. None is removed because other work may refer to it.

Original inputs under `info/` are unchanged. No branch, commit or publication is implied by these deliverables.
