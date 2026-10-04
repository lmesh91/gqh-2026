# Milestone 2 implementation contract

This is the execution plan for evidence production, not a second set of financial rules. `DESIGN.md` governs the application. The Participant Brief governs transport and physics.

## Build in this order

1. Extend the tested geometry functions without changing input ephemerides. Make all time values seconds since the original TDB epoch; scenario offsets are separate values. Persist source hashes and schema versions with each run.
2. Implement a general discrete-event transport engine. Its event queue orders by time, required sender node ID, sender packet sequence, then deterministic internal event rank. At equal timestamps, expire old packet/session state before admitting a new financial effect; this local ordering choice must be stated and tested. Preserve the brief's arrival tie-break among arrivals. Include the following separate state objects:
   - Per directed link: FIFO entries, next serialization opportunity, 10,000 cap, emitted/in-flight packets.
   - Per hop transfer: durable first-copy record, four-attempt counter, flight-based timer, outstanding receipts.
   - Per session: pinned path, SYN/SYN-ACK attempt state, final-ACK gate, byte order, 64-packet window, receive-idle expiry.
   - Per logical packet: original birth/expiry, endpoint attempts, all physical copy IDs, current byte sequence.
   - Per institution/principal: durable rolling quota deque, direct spacing, application recovery budget.
3. Build durable journal/outbox ledgers and implement the published state machines. Store immutable manifests and terminal tombstones; a simulated reset must not reconstruct balances from volatile session state.
4. Use one audit event format across all products. Every quantity change identifies the asset, owner, authority, source/export ID, available/reserved/prepared/staged status, liability and parent transaction. Mark master custody balances and derivative claims as non-additive representations.
5. Implement the futures opening escrow, relative observation schedule, fixed payoff/fallback and final allocation transaction. Use integer cents. No interim variation payout exists in version 1.
6. Generate scenario and comparative runs, then format selected evidence. Do not typeset the submission before the simulations agree with the invariants.

## Required transport tests

- Static and moving flight residuals, reverse flights at their actual later emission time.
- Exact tangent, near tangent and segment projection outside [0,1].
- Maintenance starting during flight; end boundary; original windows not replayed at shifted epochs.
- Forced loss and isolation at emission; in-flight packets unaffected by later incident start.
- Lost data, lost receipt after successful data, late receipt, four-hop-attempt abandonment.
- Endpoint retry overlaps ongoing hop retries, gets new packet ID, preserves byte sequence and original expiry.
- Retry enqueued during closure counts; replaces older unlaunched endpoint copy.
- Final ACK lost; early data held until a repeated SYN-ACK triggers another ACK.
- Queued data at 64-packet window; head-of-line blocking and FIFO queue overflow.
- Session reset while a packet is in flight; old-session data ignored; durable packet records retained.
- Seven-day idle expiry; 30-day packet expiry; rolling quota boundary at exactly 24 h.
- Direct 60 s spacing, sender-specific quota, optional reply loss, quota-consuming application resubmission.
- Equal-time arrivals from different gateways ordered by node ID then creation sequence.

## Required financial tests

- Two concurrent reservations cannot exceed available cash or custody inventory.
- One reservation split into partial fills cannot spend the residual twice.
- Cancel before order, cancel before match, cancel after match, cancel after commit.
- Decision cutoff does not unlock a YES participant; terminal abort cannot be reopened.
- Reset between journal commit and outbox enqueue is handled by atomic journal/outbox durability.
- Commit reaches only one source; no destination becomes spendable.
- All applied, one release lost; released party can spend without reusing the other party's debited funds.
- Transfer of delegated shares changes master custody exactly once and freezes the prior home sublot.
- Different sessions carry the same app ID; changed payload under the same ID rejected.
- Replayed command below a compacted closed-through floor rejected.
- Duplicate/future/late/conflicting price observations; maturity fallback after cutoff immutable.
- Both derivative directions, prices beyond the cap, insufficient opening/extension collateral.
- Clearer authority migration rejected while old active obligations or unreachable custody acknowledgments exist.

## Scenario output schema

For every financial transition: absolute time, relative scenario time, actor, local knowledge, trigger/request/packet ID, channel, durable state before/after, source lot, owner, location, liability, encumbrance, and whether the action is reversible.

For every physical launch: route/session/packet/copy/hop ID, sender node, receiver node, creation/ready/enqueue/emission/arrival time, photon distance, solar clearance, loss probability, forced-loss state, random draw, disposition, quota charge, attempt counters and queue/window occupancy.

For every run: input hash, seed, reset/relocated account, scenario offset, maintenance enabled, incident hidden schedule, admitted workload, end condition and full list of unresolved funded obligations.

Metrics: per-asset conservation; peak cash and each share encumbrance; integrated asset-hours; contract exposure; notional/value settled; direct and backbone launches plus quota originations; packet efficiency only for completed transactions; backed-claim/discharge/spendable and coordinator-knowledge times separately; maximum queues/windows; service outage duration and financial recovery time.

## Evidence acceptance gates

- S1: all required products/path directions/scale/constraint cases, exact loss-conditional traces and end-state funding.
- S2: documented incident search, chosen candidate, maintenance-off comparison and one same-guarantee alternative; no oracle knowledge of hidden incident.
- S3: all nine settlements at hours 0/300, all required authorities, comparable best/median/worst clients, no added capital.
- E1: current validated physics plus compact standalone numerical example.
- E2: traffic includes transport controls and receipts, direct deadline probability handles dependencies, hop bounds state their assumptions.
- E3: machine conservation and exclusive-backing assertions after every financial event, not merely terminal totals.
- E4: retain Tier 2 unless refined sequential route/window ranges justify Tier 3. Sub-hour grazing events cannot be dismissed by hourly sampling.
- E5: full shifted runs +1/+10/+100 years and the chosen difficult epoch; both price directions or a valid symmetry proof that includes differing payout routes.

Both price directions have symmetric payoff funding, but **not necessarily symmetric network completion** because the winner's home differs. A payoff formula alone cannot justify skipping the second difficult-epoch run.

The visual website in Milestone 3 should replay this same model and audit stream. It should not invent a separate fast animation model whose balances or transport differ from the scored evidence.
