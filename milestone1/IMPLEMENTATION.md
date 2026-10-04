# Milestones 2–3 handoff — design version 3

`DESIGN.md` is the current application specification; the Participant Brief governs physics and transport. This handoff replaces the v2 per-order reservation plan. It does not claim the separate agent's current Milestone 2 code has been migrated. No downstream files were edited by this Milestone 1 revision.

## Migration checklist

| Replace or revise | Required v3 behavior |
|---|---|
| Home reservation bound to exact order | Available account balance at each host, funded by explicit transfers |
| PAY_REQUEST / PAYMENT for every fill | Host-local funding check and order hold, then atomic local cash/share exchange |
| All-or-none assumption | Price-time matching, partial fills and residual holds |
| Per-order remote payment cancellation | Host-local cancellation/expiry; only unfilled quantity released |
| Implicit refund on delegation expiry | Host withdrawal debit/export; home imports once; never unilateral refund |
| Contract-tagged deposits | Generic trading balances, separate accepted instructions and margin holds |
| Required OPENED broadcast to homes | Position authority at host; client status uses counted direct/local access |
| Old host fill equals remote completion | Record host execution and each home import separately |
| 45 transmissions / 3.067 h treated as current evidence | Rerun v3 funding, client instruction policy, withdrawals and transport controls |
| Two-clearinghouse placement objective | Evaluate market location with prefunding, inventory, repeated trade workload and final sweeps |

Keep old protocol identifiers only as explicitly versioned comparison models. Do not relabel v2 results as v3. A paper or website headline must state the application version actually executed.

## Build and validate

1. Reuse validated frozen geometry. Do not change ephemerides, shift the initial physical epoch by the fictional year label, or repeat one-time maintenance in shifted runs.
2. Implement the complete discrete-event transport independently of financial state: directed FIFO/capacity, pinned sessions, final-ACK gate, retry overlap, hop receipts, endpoint acknowledgments, closure waiting, loss at emission, reset, lifetime, retention and quota histories.
3. Implement durable host account ledgers. Available funds, order holds, contract escrow and exports are disjoint. Commit journal and outbox together. Only authentic source transfers create imports; only the host's atomic operations reallocate its balances.
4. Implement local matching with partial fills, price-time priority, authenticated direct/local commands, duplicate outcomes, cancel-before-order tombstones, explicit expiry, capacity limits and retained/auto-withdrawn results. The bounded Milestone 1 model validates ledger transitions but is not the full matcher.
5. Implement withdrawal/close and restricted returns for late deposits. Reserve receive/return capacity and prevent loops through closed accounts. Dynamic account generations and authority migration need explicit durable rules from DESIGN.
6. Implement futures from host available balances: pending instruction holds, atomic opening, opening deadline, local price observations, fixed 24-hour fixing grace, terminal allocation and actual home payouts. Margin must compete with other account uses.
7. Implement the fixed-width codec and real batching. The Python reference objects and JSON logs are not proof of packet encoding. Reject overflow and overlength records before accepting a financial obligation.
8. Produce full scenario evidence before typesetting claims. Website views must use the same event stream and authoritative state as the evidence.

## Transport acceptance tests

Retain all tests required by the brief, including:

- Moving receiver/reverse flight residuals, tangent/near-tangent solar exclusion and segment endpoints.
- Maintenance flight-overlap boundaries; no repeated windows at shifted epochs.
- Hidden loss/isolation at emission; already in-flight photons unaffected by later incident start.
- Lost data versus lost receipt, late receipt cancellation, four-hop-attempt abandonment.
- Four endpoint attempts, timer starts at enqueue, byte sequence/original lifetime retained across new packet IDs, older unlaunched retry replacement, overlapping hop attempts.
- Lost final ACK and repeated SYN-ACK; receiver withholds application data until final ACK.
- Directed one-packet-per-second FIFO, 10,000 newest-drop overflow, 64-packet unacknowledged window, head-of-line blocking and arrival tie order.
- Seven-day receive-idle expiry, reset with durable packet/financial records retained, old-session packets ignored.
- Thirty-day packet expiry and packet-ID retention; fresh application recovery costs quota.
- Rolling 24-hour quotas and direct 60-second spacing, including direct client reports and replies.
- Batch shared-fate loss; no independent-probability shortcut for records in one packet.

## Financial acceptance tests

The current 23 bounded tests cover core equity ledger operations and payoff arithmetic. Extend them against the full implementation:

- A home transfer debits before import; duplicate import/receipt/retry changes no balance. Missing receipt never refunds.
- Host may use imported money before its receipt reaches source, including paying a seller who withdraws it to a different home. Do not count source memorandum backing as a second asset.
- Multiple orders, margin instructions and withdrawals cannot collectively exceed available balances; cash at a different exchange cannot cover a shortfall locally.
- Partial fills at equal/better prices preserve residual buy-limit holds and release only improvement. Multiple counterparties cannot overfill an order. Exclude self-trades.
- Cancellation before order, before fill, between fills and after final fill has the specified durable outcome. Cancel/expiry releases only remaining holds. Changing terms needs new identity and priority.
- An order rejected before funding stays rejected when replayed after funding. No hidden automatic investment when a top-up arrives.
- Withdrawal and new-order/fill races serialize. Retrying ALL_AVAILABLE repeats its first evaluated export rather than sweeping newly arrived funds.
- Same request/transfer/execution ID with changed payload rejects. Reset between fill/export and send preserves atomic effects and outbox.
- Auto-withdrawal has outbox capacity reserved before fill. Multiple partial fills have explicit export/receipt costs even if packet batching reduces launches.
- Account CLOSE stops new admission, cancels residual orders, leaves live contract escrow intact, and drains later proceeds. Late top-up to old generation imports once into restricted return balance and cannot silently reopen trading.
- Source and destination generation migrations cannot discard old exports or invalidate funded recipients. Returns converge to a valid home and never bounce forever.
- Master registry, delegated custody and beneficial subledgers reconcile; remote sale inventory returns through the registry before matching. A master allocation is not another unit of stock.
- Accepted contract instructions hold funds locally while awaiting the counterparty. Cancellation/opening/deadline races are atomic. Failed opening releases host holds rather than inventing a remote refund.
- Observations enforce identity, schedule, duplicate/conflict rule and fixed cutoff. Final fixing is immutable. Fixed grace is included in capital time.
- Both payoff directions/extremes conserve escrow; margin return is counted once, separate from net payoff. Q=2,501 fails Cara's capital constraint.
- Closing/recovery never releases live margin early; maturity during isolation creates funded pending payout exports.
- Backpressure, active windows, terminal acknowledgment and compaction floors preserve all old obligations and reject stale commands for arbitrarily delayed packets.

## Quota and scheduling policy

Enforce 66 backbone originations per institution per rolling day, split 44 routine/22 recovery: aggregate594. Include new SYN, TRANSFER, RECEIVED, status, registry legs and application resubmission. Exempt automatic transport retries/ACKs/receipts only as the brief allows. Enforce direct quotas across all accounts sharing a principal.

Choose and declare a causal client instruction policy. A scheduled order after a nominal funding delay may arrive too early and be rejected. A client waiting for confirmed funding needs a real counted report. The harness may audit global state but must not let client decisions secretly read remote ledgers or hidden incidents.

Orders can create many partial fills and automatic withdrawal records; aggregate funding limits alone do not bound that traffic. Stress client-command batches, fragmented liquidity, many counterparties and concentrated maturities. Paid transfer recovery has priority; unbounded new demand cannot force record deletion.

## Audit and reporting

For every transition record absolute/scenario time, actor, authenticated trigger, request/order/execution/export IDs, local knowledge, asset, beneficial owner, custodian, available/held/escrow/export/import amounts, source ledger evidence and resulting state. Financial totals must reconcile after **every** event. Grouped unaffected accounts are insufficient for the final E3 appendix.

For every physical launch record route/session/packet/copy/hop IDs, sender/receiver, creation/ready/enqueue/emission/arrival times, geometry/clearance, loss probability/draw/incident outcome, retry counters, quota charge, queues/windows and disposition. Count all controls and receipts in communication efficiency.

Report separately:

- Host execution/final allocation, transfer-backed claim, home spendability, source receipt knowledge and client notification.
- Unreserved cash at remote accounts, order/position encumbrance, in-transit value, asset-hours and time away from home. Unused prefunding is not open-position margin.
- Cash/share conservation, maximum exposure, peak margin, host matched turnover separately from home-delivered value/notional, and gross payouts versus net profit. An intermediate retained/resold fill is not retroactively home-delivered by a final net sweep.
- Offered/admitted workload, order rejections, cancellation effectiveness, direct and backbone usage, capacity deferral, and unfinished funded obligations.

Every run records source/model hashes, version3, seed, opening/reset/relocation, epoch offset, maintenance state, hidden incident and stopping condition.

## Evidence acceptance gates

S1: original funding book; actual funding before trading; equity with home delivery; 300-hour futures in both paths; >=25% cash encumbered by open positions; binding capital variation; all terminal/pending obligations named and funded.

S2: choose an allowed incident using documented search; include later-price product; compare maintenance-off and a same-funding/same-home-guarantee alternative such as automatic withdrawal versus final sweep. Count changed delivery times and all control traffic.

S3: all nine settlements at hours0/300, relevant asset markets and Mars contract funding/payout; comparable relocated best/median/worst accounts without extra wealth. A forward link to Mars alone does not establish full service access.

E1–E5: retain geometry evidence with its stated sampling limits; rerun application traffic and account audits under v3. For +1,+10,+100 years and chosen difficult epoch, preserve orbital phase conventions, shift observation/maturity schedules and do not replay original one-time maintenance. Run both price directions unless network symmetry is actually demonstrated.

## Website handoff

Display balances by host and state; provide funding, order, cancel, partial-fill and withdrawal scenarios. Show that a Mars fill can be final locally while home delivery is pending. Include the $10k/two-order example and fill/cancel/withdrawal races. Scenario controls must manipulate the shared simulator, not an independent animation model. All “complete,” “available” and “packet saving” labels must use the same definitions as the paper.
