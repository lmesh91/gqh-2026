# Milestone 2 implementation contract — design version 2

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
4. Use one audit event format across all products. Every quantity change identifies the asset, owner, authority, source/export ID, available/reserved/promised/exported/imported status, liability and parent transaction. Mark master custody balances and derivative claims as non-additive representations.
5. Implement the futures opening escrow, relative observation schedule, fixed payoff/fallback and final allocation transaction. Use integer cents. No interim variation payout exists in version 2.
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

The existing 27 tests in `test_direct_settlement.py` cover the bounded equity model and payoff arithmetic. Extend them against the durable implementation and full transport engine:

- Concurrent reservations cannot exceed available cash; each immutable reservation funds exactly one order at exactly one market.
- Identical retries return the same decision; a changed payload under the same ID is rejected. A second transaction cannot consume an already paid reservation.
- Reject partial fills and in-place amendments in the baseline. Price improvement releases only the unused budget; it does not reopen the reservation.
- Serialize cancellation, expiry, VOID and payment at the home. Unpaid cancellation releases cash; payment first prohibits refund. Paid evidence stays valid after the acceptance deadline.
- A market timeout never releases promised shares without definitive source NO_PAYMENT. A delayed PAYMENT requires delivery even after quote expiry.
- A definitive refusal cannot be changed into payment by late packets, session replacement or reset.
- Cash import, seller credit and share export at the market are one durable local transaction. Duplicate delivery cannot create shares twice.
- Reset between journal commit and send preserves the decision and outbox. RECEIVED loss changes recovery work, not buyer spendability.
- Transfers cannot credit without matching source debit; late or duplicate transfers cannot be refunded at the source. Remote inventory and proceeds are charged transfers.
- Replay below a compacted closed-through floor is stale; gaps and unresolved obligations prevent unsafe compaction.
- Bogus reservation traffic cannot exceed provisional match caps or spend another client's cash. Measure the resulting inventory unavailability.
- Collateral funding, client instructions and OPENED messages are distinct. Open only after both instructions and both credited contributions; late funding after the opening deadline must return through an irrevocable transfer.
- Price observations reject unauthorized, future, late and duplicate/conflicting values according to DESIGN. Fixing is immutable; a later conflicting observation cannot reopen allocation.
- Both derivative paths and prices beyond the cap conserve the escrow. No interim cash payment exists; final payout includes returned collateral exactly once.
- Simultaneous final allocation and both payout exports cannot allocate more than the escrow. Different home arrival times produce different local spendability times.
- Insufficient funding rejects opening. Position enlargement needs a separately funded contract.
- Account, registry or authority migration cannot invalidate an accepted export or create a second spending authority.

## Application and quota acceptance

Implement the 66-originations-per-exchange rolling budget (44 routine, 22 recovery), totaling 594. Include new SYN, status/void messages, OPENED, transfer receipts and application retries. Use the real rolling history rather than calendar-day resets. Admission limits and paid-obligation priorities must operate under concentrated demand, not only evenly distributed requests.

Implement fixed-width serialization before relying on packing estimates. Validate lengths against the 960-byte application payload, versioning, integer overflow, authenticated identity and the complete immutable order/contract digest. Do not treat the prototype's Python/JSON objects as the final wire encoding. Batching must preserve per-record authorization and cannot delay safety responses indefinitely.

The current trace engine deliberately omits random loss, general queue overflow, retry races and sustained offered load. It must not be promoted to the full simulator by adding independent delay samples. Transport and application state must interact causally.

## Scenario output schema

For every financial transition: absolute time, relative scenario time, actor, local knowledge, trigger/request/packet ID, channel, durable state before/after, source lot, owner, location, liability, encumbrance, and whether the action is reversible.

For every physical launch: route/session/packet/copy/hop ID, sender node, receiver node, creation/ready/enqueue/emission/arrival time, photon distance, solar clearance, loss probability, forced-loss state, random draw, disposition, quota charge, attempt counters and queue/window occupancy.

For every run: input hash, seed, reset/relocated account, scenario offset, maintenance enabled, incident hidden schedule, admitted workload, end condition and full list of unresolved funded obligations.

Metrics: per-asset conservation; peak cash and each share encumbrance; integrated asset-hours; contract exposure; notional/value settled; direct and backbone launches plus quota originations; packet efficiency only for completed transactions; backed-claim/discharge/spendable and market-knowledge times separately; maximum queues/windows; service outage duration and financial recovery time.

## Evidence acceptance gates

- S1: all required products/path directions/scale/constraint cases, exact loss-conditional traces and end-state funding.
- S2: documented incident search, chosen candidate, maintenance-off comparison and one same-guarantee alternative; no oracle knowledge of hidden incident.
- S3: all nine settlements at hours 0/300, all three baseline asset markets and the Mars contract host, comparable best/median/worst clients, no added capital.
- E1: current validated physics plus compact standalone numerical example.
- E2: traffic includes transport controls and receipts, direct deadline probability handles dependencies, hop bounds state their assumptions.
- E3: machine conservation and exclusive-backing assertions after every financial event, not merely terminal totals.
- E4: retain Tier 2 unless refined sequential route/window ranges justify Tier 3. Sub-hour grazing events cannot be dismissed by hourly sampling.
- E5: full shifted runs +1/+10/+100 years and the chosen difficult epoch; both price directions or a valid symmetry proof that includes differing payout routes.

Both price directions have symmetric payoff funding, but **not necessarily symmetric network completion** because the winner's home differs. A payoff formula alone cannot justify skipping the second difficult-epoch run.

The visual website in Milestone 3 should replay this same model and audit stream. It should not invent a separate fast animation model whose balances or transport differ from the scored evidence.
