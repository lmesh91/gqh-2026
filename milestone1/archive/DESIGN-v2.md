# Milestone 1: direct settlement between planetary exchanges

**Design version 2.0. This is the current rulebook.** It supersedes `archive/DESIGN-v1.md`, including the separate Mars/Neptune clearing assignment and the universal prepared/committed/applied/released cycle. The governing specification remains the Participant Brief released October 2, 2026 and the frozen `info/data.zip`. No organizer clarifications were supplied.

This document specifies the system for Milestone 2. It is not the 12-page submission paper. Implemented examples, model checks, proposed experiments, and extensions are distinguished explicitly. `SIMPLIFICATION.md` explains changes and comparisons; `IMPLEMENTATION.md` gives the remaining evidence work.

## 1. Recommended system

Each of the nine settlement exchanges runs its local accounts and the order books, share registry, and contract administration for its assigned assets. **The exchange running a market also coordinates that market's settlement. There are no separate clearinghouse institutions or mandatory remote clearers.** Nine exchanges use nine of the twelve allowed institution identities. Remaining identities are not used to obtain extra capacity.

The ordinary remote share purchase follows the user's proposed sequence:

1. Buyer reserves cash at its home exchange for one specific order at one specific market.
2. Buyer sends the order and reservation number directly to that market.
3. Market provisionally matches the order, promises the seller's shares for that transaction, and asks the home exchange for the exact payment.
4. Home validates and consumes the reservation, durably records the payment debit/export, and sends confirmation.
5. Market records the payment, credits the seller, debits the promised shares into a transfer to the buyer, and sends the share-transfer record.
6. Buyer home credits the shares once and confirms receipt.

Official exchange-to-exchange messages use the backbone. A reservation number carried by a client is a reference, not proof of funding. Local transactions inside one exchange use one atomic ledger operation; they do not run this remote protocol.

**Core scope:** fully funded equity orders, transfers, and a capped cash-settled futures contract. Orders are all-or-none against one counterparty and each reservation is single-use. Partial fills, in-place amendments, arbitrary atomic baskets, unbounded leverage, and portfolio margin are extensions, not silently supported features.

**Important tradeoff:** the buyer's reservation is checked on demand, after the market has promised inventory. An invalid reservation can therefore temporarily tie up shares. Bounded provisional matches and recovery protect capital and storage but cannot make this availability risk disappear. Prior funding verification is an optional paid-for optimization, not an assumed free service.

### What is authoritative

| Record | Sole writer |
|---|---|
| Spendable cash, reservations, and payment decision | Exchange currently holding that cash |
| Market order book, provisional matches, immutable trade details | Asset's market exchange |
| Master share registry and aggregate custody allocation | Asset's registry exchange, collocated with its market in the baseline |
| Beneficial share balances inside a delegated custody allocation | The home exchange holding that allocation |
| Share delivery and seller payment recorded at the market | Market exchange |
| Buyer's local receipt and local spendability | Buyer's home exchange |
| Derivative terms, position, fixing, and final allocation | Exchange hosting that contract |

An institution may hold a customer's custodial balance without owning it. Institutional opening capital remains zero. A clearer role does not itself create capital, insurance, or an independent financial guarantee.

### Trust boundary

Brief Section 3, page 7 says operators follow the rules but may crash, reset, or lose connectivity; malicious or colluding operators are an optional extension. The baseline therefore handles strategic clients and communication failures, not dishonest custodians or fabricated operator certificates. Combining matching and settlement is consistent with that baseline. An independent organization would only improve malicious-operator protection if it independently verified records and its approval was mandatory; merely relaying the same assertions would add messages without establishing that protection.

Authenticating a source statement does not prove an operator's honesty. All debit and custody evidence below relies on the brief's honest-operator assumption and durable records. No Byzantine-security claim is made.

## 2. Requirements and invariants

### Source hierarchy and physical model

The brief's Section 2 fixed-parameter tables govern in case of disagreement with other brief text. The archive's orbital elements and network model govern baseline geometry. The architecture sketch and exported daily positions are design/reference inputs. No live ephemeris replaces the frozen model.

The archive contains twelve files: the orbital and network JSON, README, and nine Horizons responses. It does not contain the reference propagator mentioned in the brief. Our own implementation follows the stated equations and printed epoch checks. Six sampled dates in the separately exported CSV agree with that implementation to within 5.39×10⁻⁹ AU, but its provenance is not independently established; it is not used for sub-day flight calculations.

| Brief requirement | Current implementation/design consequence |
|---|---|
| Epoch 2026-09-22 00:00:00 TDB; 2126 is fictional label | Model time is elapsed seconds from the physical epoch; no initial 100-year shift |
| Fixed Kepler ellipses; Sun-centered 3D J2000 ecliptic AU | Use supplied mean motion and elements; negative time uses backward propagation |
| Relays at √8 AU, phases 45°/135°, prograde circles | Supplied relay parameters, not movable or additional infrastructure |
| Light time 8.317 min/AU; moving receiver; 1 ms tolerance | Solve arrival iteratively, reverse paths at their actual later emission time |
| Solar exclusion 0.10 AU | Check closest point of sender-at-emission/receiver-at-arrival segment |
| Nineteen bidirectional backbone links | Gateway–A, gateway–B, A–B only; no direct gateway backbone edge |
| Simple pinned routes, at most three links | Enumerate A, B, A→B, B→A; replacing a session requires a new handshake |
| 1 s serialization each launch; 1 s relay processing | Separate enqueue, readiness, emission, arrival, next-hop readiness |
| Client local access 1 s, lossless; direct has access at both ends | No local-access charge on backbone; same-site client instruction is local, not a direct packet |
| Independent launch loss: backbone 1−e^(−0.02d), direct 1−e^(−0.08d) | Apply to actual photon distance for every launch, including receipt/ACK directions |
| Packet 1024 bytes, header 64, payload 960, fixed-width/uncompressed | Bounded records and explicit packet counts; no hidden compression or unlimited certificates |
| Global backbone quota 600 originations per rolling 24 h | Static institution sub-budgets enforce it without a synchronized global counter |
| Direct 12 per principal per rolling 24 h, launches ≥60 s apart | Client copies, replies and institution direct traffic each use the sender's own allowance |
| SYN, initial application/control packets, resubmissions charged | Automatic retries, transport ACKs and hop receipts exempt from origination quota, not communication totals |
| Directed FIFO 1 packet/s, queue 10,000, newest dropped | Enforce serialization and bounded application backlogs; transport congestion can delay progress |
| Simultaneous arrivals: sender node ID then packet creation sequence | Authoritative sequencing follows the brief; client timestamps do not grant priority |
| Hop timer 2×flight+60 min, at most four launches | Receipt loss is different from data loss; receipts have no receipts of their own |
| Handshake SYN/SYN-ACK/ACK, receiver gates data on final ACK | No financial action merely because a SYN or transport ACK arrived |
| Endpoint timer 2T0+24 h, at most four attempts | T0 includes moving flights/serialization/relay processing, excludes queues/closure waits |
| Endpoint retry gets new packet ID, keeps byte sequence and original lifetime | Counts when enqueued; replaces older unlaunched copy; may overlap hop retries |
| Window 64 unacknowledged data packets; application delivery in order | Stricter application window of 16 used by policy; full simulator must enforce transport window too |
| Session idle expiry 7 days, IDs never reused | New handshake after expiry/reset; no exemption for recovery sessions |
| Packet lifetime 30 days; packet duplicate retention lifetime plus 30 days after last receipt | Transport expiry never cancels paid transactions or unresolved delivery obligations |
| B–Neptune [2,26), B–Ceres [240,264), once, both directions | Prevent launches whose flight interval overlaps maintenance, even before the window starts |
| Isolation 72 h, forced loss 6 h, or endpoint reset; incident unannounced | Harness applies at emission; actors cannot route using advance knowledge of hidden incident |
| Endpoint reset preserves financial records and packet-ID records | Durable application outbox rebuilds work through new sessions; old-session packets ignored |
| All shared financial-state changes use backbone | No direct client-carried reservation, payment proof or certificate may substitute for official coordination |
| Opening ≤$500k, ≤5000 shares, 4–10 accounts at ≥3 settlements; institutions zero | Six-account book in Section 8; no hidden reserves or pre-epoch finance |
| ≥240 h obligation; two products; separate rising/falling ≥20% paths | Equity plus 300-hour capped futures, fixed rule in both directions |
| ≥25% cash encumbered; real constraint must bind | $160k futures escrow =32%; oversized position rejected for insufficient cash |
| Local spendability and matching debits define completion | Approval, payment, backed claim, discharge, spendability and knowledge are reported separately |
| All nine settlements access a later-price product | Funded access to the Mars contract through actual escrow transfers; no permanent exclusion |
| Indefinite market, finite accepted demand/storage/IDs | No window resets financial state; explicit caps, backpressure and engineering lifetime |
| S1–S3, E1–E5; ≥200 Julian years and shifted epochs | Existing geometry plus revised v2 traces; full scenario evidence still Milestone 2 |
| Paper 12 pages, appendix 12 pages, ≥10 pt, margins ≥1 inch | This research report is not the final submission; source assistance rules and clarifications still apply |

### Safety invariants

1. Opening assets equal available balances + reserved/escrow balances + uniquely counted exports in transit. A claim on an export is not a second asset.
2. Every reservation is bound to one owner, source, market, order ID, immutable order terms, and amount. It becomes paid at most once.
3. A source payment decision for a transaction is durable and terminal: PAID or NOT_PAID. A retry cannot change that decision or create another debit.
4. The seller's promised shares remain unavailable to other trades until the source proves NOT_PAID, or the market delivers those shares against the recorded payment.
5. Before the seller's proceeds become spendable, both the buyer's payment debit and the seller's share debit are recorded. Before the buyer's shares become spendable, that home has its own payment debit and the market's matching delivery record.
6. The same imported cash or share export can be credited once only. Master custody totals and beneficial balances are two views of the same stock, not additive holdings.
7. Every accepted later-price obligation is backed by maximum-loss collateral; no promise assumes a future margin call or liquidation can get through.
8. Session/packet/scenario expiry does not erase financial history. An unpaid local reservation may expire safely only because the source permanently prevents subsequent payment against it.

Assumptions beyond network rules: durable atomic local journal/outbox writes, local computing/storage within admitted limits, correct operator execution, and registered destination accounts/custody rules fixed for each accepted transaction. Permanent destruction of durable storage is outside the baseline. Safety does not require delivery eventually; liveness does.

## 3. Market location, custody and product scope

### Keep markets with their assets

The baseline leaves Ares Habitat's market on Mars, Belt Works on Ceres, and Terra Fabrication on Earth. Other registered instruments can have markets at any of the nine exchanges. An asset has one market; listing it on two independent books with a shared backing budget is not supported.

Keeping market and settlement coordination together removes a market-to-clearer proposal and remote coordination with a third site. A trade between Earth and Ceres does not involve Mars. The earlier Mars/Neptune placement screen measured distance to potential clearers, not full transaction cost, and is **not evidence for centralizing order books**.

Moving all markets to Mars/Neptune is feasible but not the baseline. It cannot silently move the customers' opening assets. For example, moving the Belt Works market to Mars while Cara's shares and home remain on Ceres requires inventory delivery to Mars before sale and proceeds delivered back to Ceres afterward. These transfers, direct seller instruction, custody changes and capital-hours must be counted.

Under the declared all-two-hop, cold, unbatched packet accounting, the Earth–Ceres trade at its local Ceres market costs 45 transmissions. A Mars-hosted version with a new Ceres–Mars session, upfront share delivery/receipt, later cash proceeds/receipt reusing that session, and a remote seller order would cost **90 transmissions and 10 backbone originations**, versus 45 and 5 locally. This is a structural count for those assumptions, not an executed timing result or proof that decentralization is optimal for every workload. Already-funded hub inventory can change marginal costs, but its initial transfer is not free.

### Cash and shares at home

NeoDollars are conserved ledger assets, not separately issued planetary currencies. An export first debits its source and identifies destination, owner, beneficiary, asset, quantity and unique export ID. Until import, it is funded value in transit. Destination import credits it exactly once. An acknowledgment closes the sender's recovery work, not a second transfer.

A remote share receipt allocates an exclusive custody lot to the recipient's home. The master registry records that aggregate allocation; the home records beneficial owners inside it. Local transfers within the allocation do not create another master share. To sell such shares on the remote master market, their current home first debits/exports them back into the owner's market inventory, and the market receives them before allowing an executable sell order. No simultaneous selling at home and at the market is possible.

This inventory-first rule deliberately replaces arbitrary multi-authority share settlement. It costs an explicit transfer when stock is held remotely but avoids having to atomically coordinate an unverified third-party stock source during the sale. Unused inventory remains the client's asset, can be returned through the same transfer primitive, and counts in encumbrance measures whenever committed to an order.

If the seller's home differs from the market, crediting proceeds at the market is **not final local completion**. The market debits that custodial proceeds balance into a cash export to the seller's home. Completion waits for that home and the buyer's home to credit their respective results. Proceeds awaiting export remain reserved for the seller and cannot fund another client or the institution.

### Supported service at each of the nine settlements

| Product | Local service and remote access | Conditions |
|---|---|---|
| Local transfer/trade | One atomic local operation on unlocked cash and delegated/locally held shares | Sufficient local inventory; no network transaction manufactured |
| Cross-settlement transfer | Debit/export → destination import → receipt | Valid registered destination; delivery may remain pending, fully funded |
| Equity purchase | Direct client order plus exchange-to-exchange payment/delivery | One reservation, one all-or-none order; seller inventory already at the market |
| Capped futures | Send funded collateral to the hosting exchange; position and fixing there; payouts sent home | Maximum-loss escrow; explicit oracle/terms; funded delay during outages |
| Bonds, lending, options, borrowed-stock shorts, new currencies | Extension templates only | Must separately specify payouts, funding, default and routing; not advertised as implemented |

All nine sites may access the Mars futures product even without a locally originated index. Local free assets continue to be usable during gateway isolation. No universal completion deadline is promised.

## 4. Reservation, order and duplicate rules

### One reservation = one immutable order

The source records:

`(source, owner, reservation_id, authorized_market, registry_version, order_id, asset, side, exact_quantity, maximum_price, reserved_cash, order_expiry, state)`.

Reservation identity includes the source and owner; it is not a globally unique bare integer or a secret bearer token. Principal authentication and ownership checks remain mandatory. The source allocates durable nonreused reservation IDs. For a buy, `reserved_cash = quantity × maximum_price`, with no fees in version 2. Amounts are integer cents and quantities are integer share units; reject non-integer values, negative values and wire overflow.

The reservation is not a general-purpose wallet. Two orders cannot each claim its whole amount. To submit two independent orders, the client needs two reservations, and the source atomically removes both amounts from available cash. If $100k is reserved from $150k, a second $100k reservation fails; two $50k reservations can both succeed.

The receiving market permits one active proposal per qualified reservation and checks authenticated client identity. The source independently checks the entire stored authorization before paying. This source-side check is decisive: even if two requests reach different queues, the reservation's atomic RESERVED→PAID transition occurs once.

A client request ID persists across sessions. Identical retry returns existing status. Same ID with different payload is rejected. A new request ID is a new instruction, not evidence of additional backing. A guessed reservation belonging to another client cannot debit that client or cancel its genuine authorization. A malformed proposal can be refused without poisoning the owner's genuine reservation.

### Order semantics and priority

Only exact-quantity, all-or-none, limit or marketable-limit orders are supported. The baseline matches one buyer with one seller. It does not partially fill against several makers or silently change quantities. A customer can intentionally split an order into separately funded smaller orders. Modification means cancel and submit a new order with a new reservation; there is no in-place price/quantity amendment.

The market sequences complete authenticated client instructions by application receipt. Truly simultaneous arrivals follow the brief's sender node ID, then packet creation sequence; batch record index is the final local tie rule. Local instructions use the local gateway and its monotonically assigned creation sequence. Better price then earlier eligible receipt ranks market orders. Client creation timestamps never grant priority.

Buyer orders use immediate-or-cancel matching: if no single eligible seller has enough listed inventory at the limit, reject without a provisional match. Seller inventory offers rest until their declared expiry/cancellation; held quantities cannot be withdrawn while payment is unresolved. A rejected buyer order needs a new order/reservation to try again; an identical retry only returns its recorded outcome. The buyer may cancel its unused home reservation locally. Once provisionally matched, its shares are withheld from other matches until payment is resolved. There is no final execution claim until the payment-backed delivery is recorded. This differs deliberately from v1's preconfirmed-funding priority and admits a bounded availability risk from unverified orders.

### Expiry and cancellation are asymmetric

**At the buyer's home:** if the reservation is still unpaid, a local cancellation or order-expiry event can release cash immediately, atomically leaving a permanent CANCELLED/EXPIRED record. Every later payment request against that reservation is rejected. This is safe because the market never delivers stock solely from the reservation number. If a payment was already recorded, cancellation returns PAID/PENDING_DELIVERY and does not refund anything.

**At the market:** an unmatched order can be cancelled immediately. A provisional match with an outstanding payment request cannot release its shares merely because a timer expired. Payment may have been recorded while its confirmation was lost. The market sends a status query or `VOID_REQUEST` to the source. Source atomically returns either the existing PAYMENT or a durable NO_PAYMENT for that exact transaction. Only NO_PAYMENT releases the provisional shares.

`VOID_REQUEST` racing PAY_REQUEST is serialized at the source. Void first → permanent NO_PAYMENT; payment first → return the same PAYMENT. Source cancellation of the whole reservation and voiding one proposal are distinct: a rejected proposal may leave an otherwise valid reservation unused until its owner cancels or it expires.

PAY_REQUEST includes an acceptance cutoff `min(order_expiry, proposal_time +24 h)`. The source must record a first payment before this cutoff. A replay of an already-recorded payment remains valid after it. The cutoff limits authorization; it is not a time by which the market can infer NO_PAYMENT. A reservation expiry and a transport packet expiry have completely different meanings.

### Bounding provisional inventory abuse

At most one outstanding provisional match per authenticated client at a market, and at most eight per market in the baseline. These caps apply across new request IDs. New requests cannot displace already promised inventory. A source NO_PAYMENT releases the shares, and repeated invalid requests consume that principal's own direct quota and can be admission-throttled. Operator replies are budgeted, never a free global verification service.

These controls limit resource use but do not eliminate denial of service against scarce stock: even one bogus request can immobilize a scarce lot while its supposed source is unreachable. Never “solve” that by unsafe timeout release. For a market suffering this workload, prior official reservation verification is an optional alternative requiring additional backbone traffic; it must be compared under identical funding and included quotas. The primary protocol remains on-demand verification.

## 5. Direct trade protocol and finality

The market issues an immutable PAY_REQUEST only after recording its promised share lot and an outbox entry in the same durable transaction. This is a conditional delivery commitment: if the source pays that exact request, the market owes those shares. It may not rescind the promise unilaterally while the payment outcome is unknown.

| Message / step | Sender → receiver | Durable effect and knowledge |
|---|---|---|
| Local RESERVE | Client → home, local | Cash becomes reserved for one exact order; client receives reservation ID |
| ORDER | Client → market, direct/local | Provisional match; market promises exact shares; no proof of cash yet |
| PAY_REQUEST | Market → buyer home, backbone | Exact trade, reservation, price, seller, destination and acceptance cutoff; authenticated binding share-delivery promise |
| PAYMENT or NO_PAYMENT | Home → market, backbone | PAYMENT exists only after atomic source debit/export and reservation consumption. NO_PAYMENT is final for that request. Identical retries return the same result |
| DELIVERY | Market → home, backbone | After PAYMENT, market atomically imports cash, credits seller, debits/exports promised shares and persists delivery/outbox. Incoming cash is not spendable before that share debit |
| RECEIVED | Home → market, backbone | Home atomically imports exact shares against its matching payment record; receipt confirms local availability and permits terminal recovery cleanup |

There is no separate universal PREPARE, COMMIT, APPLIED or RELEASE exchange. Their necessary conditions are carried by the reservation, binding payment request, recorded payment and recorded delivery. A transport ACK still proves only byte receipt.

**Backed claim:** when the home accepts the market's promise and records payment, Alice holds a recorded claim to the promised, already encumbered shares. **Seller cash spendable:** when the market records cash import and share debit together (or later at the seller's remote home). **Buyer shares spendable:** when the home receives and records the market's share export. **Trade complete:** the later local-spendable moment, with matching debits recorded. **Market knows completion:** on RECEIVED from the last required home. These are not interchangeable.

The main traces have seller and market at the same settlement. A remote seller adds proceeds transfer and receipt; it does not get hidden “local” completion at the market.

### State machines

| Record | Allowed transitions | Who decides / what cannot time out |
|---|---|---|
| Buyer reservation | RESERVED → PAID; or RESERVED → CANCELLED/EXPIRED | Source only; PAID never automatically reverts |
| Source transaction result | NONE → PAYMENT or NO_PAYMENT | Source atomic decision per market+transaction ID+digest; terminal result immutable |
| Market order | OPEN → PROVISIONAL → DELIVERED → RECEIPT_CONFIRMED; or OPEN → CANCELLED/EXPIRED; PROVISIONAL → REJECTED on NO_PAYMENT | Market; PROVISIONAL cannot unlock on silence |
| Cash transfer | SOURCE_DEBITED/IN_TRANSIT → DESTINATION_CREDITED → RECEIPT_KNOWN | Source and destination update their own ledgers once; sender never refunds on missing ACK |
| Share transfer | SOURCE_DEBITED/ALLOCATED → HOME_CREDITED → RECEIPT_KNOWN | Registry allocation and home lot use one export ID; no duplicate beneficial balance |
| Derivative funding | EXPORT_PENDING → ESCROW_AT_MARKET → POSITION_OPEN | Market opens only after both funded contributions and instructions exist |
| Derivative | OPEN → FIXING → ALLOCATED → PAYOUT_IN_TRANSIT → SETTLED | Hosting exchange owns terms/fixing; home receipts define actual local payouts |
| Recovery | DELIVERY_UNKNOWN → NEW_SESSION/QUERY → REPLAY_SAME_RESULT → CONFIRMED | Financial record, request and export IDs survive every transport change |

Market and source keep a durable request digest, decision/result, source lot/export IDs, beneficiary, destination, timestamps and terminal acknowledgments. Contradictory authenticated terminal results are quarantined, not resolved by “latest message wins.” They indicate a bug or a fault beyond the honest-operator model.

### Why this is safe without a separate release barrier

There are only two financial authorities in the standard trade and seller inventory is already at the market. Earth cannot pay without reserving and debiting the exact cash. Mars cannot credit the seller's proceeds without also debiting the exact promised shares. Earth cannot credit the shares without the matching delivery record and its own payment debit. Thus every spendable result has its matching debit already recorded.

If PAYMENT is lost, cash is in transit and shares remain promised. If DELIVERY is lost, the seller has received payment but shares are already debited and uniquely assigned to Alice in transit. Alice cannot spend an unreceived share, and the seller cannot sell it again. If RECEIVED is lost, Alice's local balance remains valid; a duplicate DELIVERY returns the same receipt without another credit. None requires simultaneous knowledge at both planets.

A crash between credit and debit would be unsafe; that is why the market's cash import/seller credit/share debit/outbox is **one atomic local transaction**, not a sequence exposed to reset. This local atomicity replaces distributed round trips, not the underlying backing requirements.

## 6. Transfers and remote inventory

For a registered destination and admitted operation, use `TRANSFER(export_id, asset, amount, beneficiary, destination, source_record)` and `RECEIVED(export_id, destination_record)`. The source irrevocably debits the asset before TRANSFER; the destination imports exactly once. Lost acknowledgment never justifies source refund. Unknown or incompatible destination is rejected before export; existing registered accounts/custody limits cannot change in a way that invalidates already accepted exports.

The source keeps a funded in-transit obligation until receipt. The destination can spend the imported value because the matching source debit already exists. An export is not counted both as source cash and destination cash. Repeated transfer attempts carry the same financial export ID even when network/session IDs change.

Use this primitive for:

- moving owned shares into their market inventory before a remote sale;
- returning unfilled market inventory after all outstanding payment proposals are resolved;
- forwarding sale proceeds to a remote seller's home;
- transferring collateral to a contract's host and returning terminal allocations home.

This deliberately avoids a general distributed transaction covering arbitrary home cash, home stock, a separate master, and a separate clearer. It trades some prefunding transfers for fewer authority combinations and a much simpler safety argument. Their traffic and asset-hours are part of the cost, never treated as free setup.

## 7. Failure rules and continuing operation

| Event | Required action and financial outcome |
|---|---|
| Direct ORDER lost | No trade; local reservation may remain until local cancellation/expiry. No automatic direct receipt exists. Retry same ID within quota/spacing |
| ORDER received, client unsure | Same request returns the same provisional/final result; no second inventory promise |
| Bogus reservation or wrong order/market | Source NO_PAYMENT for exact request; market returns promised shares to book after receiving it |
| Multiple orders reference one reservation | Market prevents concurrent attachment; source exact-order check and single-use transition independently prevent multiple payments |
| PAY_REQUEST lost | Market cannot distinguish from a lost PAYMENT. Query/void source; keep shares promised until terminal response |
| PAYMENT lost | Source debit remains; market's stock promise remains. Replay same payment; no refund or second debit |
| DELIVERY lost | Shares already exported; seller cannot reuse them; home retries/query receive same delivery |
| RECEIVED lost | Buyer keeps shares; market repeats delivery/query and receives duplicate-safe response |
| Cancel races payment | Source serializes: cancellation first prevents payment; payment first prevents refund |
| Quote withdrawal races payment | Source VOID first gives NO_PAYMENT; payment first returns PAYMENT and forces delivery |
| Old packet after cancellation | Source tombstone prevents new payment; old already-paid evidence remains valid only for its exact transaction |
| Old message after completed trade | Immutable ID/digest returns old status, never a new balance mutation |
| Market reset after issuing request | Shares and promise/outbox survive; cannot forget the promise and rematch |
| Source reset after debit but before send | Payment/outbox survive; new session resends original result |
| Packet exceeds 30 days or session expires | Transport stops; financial liability survives; charged application recovery/new handshake |
| Gateway isolation | Local cancellation of unpaid reservations and local free-asset use remain possible; paid deliveries stay funded pending |
| Maturity during isolation | Contract host fixes/allocates using its rule and holds funded exports until delivery; no fictitious immediate remote payout |
| Backlog after reopening | Old paid obligations and receipts precede new proposals; all quotas/windows still apply |
| Malicious operator certificate | Not protected by baseline; freeze contradictions and preserve evidence. Independent verification is an extension |

### Recovery scheduling

Only resubmit at application level after transport reports delivery unknown, session reset/expiry, or a declared recovery status timer after live transport responsibility has ended. Reuse the financial transaction/export ID and immutable payload. New session SYN and application resubmission are new quota originations. Automatic hop/endpoint retries retain their exemptions and distinct packet IDs.

Application recovery backoff is 24, 48, 96, then 168 hours, capped at 168 hours and delayed further when known geometry or quota prevents launch. A newly restored usable route does not mean funds instantly become spendable. Final financial recovery requires the relevant payment/delivery/import operation, not merely a received packet.

### Quotas, demand and storage

Each of the nine exchange institutions receives a conservative **66 backbone originations per rolling 24 h**: 44 routine and 22 recovery. Total allocation is 594, deliberately leaving six of the global 600 unused. No live global counter or quota borrowing is required. Clients retain their own direct quotas. Additional accounts or institutional principals are not introduced to gain capacity.

Priorities: paid deliveries and matured payouts; receipts and definitive payment-status/void responses; return of unused assets; new funding/proposals; advisory data. Every class remains within its budget. Local admission considers its outbox/backlog; if there is no capacity it defers before accepting more risk. A committed response may wait for quota but cannot be discarded financially.

Declare a baseline offered workload of **at most one new cross-settlement trade/contract-funding operation per exchange per rolling day**, plus recovery and scheduled maturity work. This is a finite planning load, not guaranteed accepted throughput: concentrated counterparties, insufficient funds, quota exhaustion or outages can require rejection/deferment. Higher demand is throttled. Local free-asset transfers are bounded by declared local computing capacity, not the backbone limit.

Application limits: 1,024 unresolved records per home, 4,096 per market, 16 outstanding application data packets per peer, eight provisional matches per market and one per client. Reserve 20% of active-record capacity for recovery/maturity of already accepted obligations. Never delete an unresolved liability to make room. Already funded incoming transfers need durable receive/outbox capacity reserved by the admitted workload; overload pauses new exports, not recognition of an accepted liability.

Request, reservation, transfer and session identifiers use a registered principal prefix plus a durable 96-bit counter. At an engineering lifetime of one million Julian years, even 10⁶ IDs/s uses about 3.16×10¹⁹ IDs, below 2⁹⁶. 64-bit millisecond time spans about 584 million years. Reject before overflow; a future width change is a versioned migration, never wrapping or reuse.

Use a bounded 1,024-request active window and durable closed-through floors per sender/namespace. Compact completed records only after required financial receipts, safe closure of gaps, and transport retention. Old IDs below the floor are stale, not new. Retain active paid obligations regardless of age. Packet-ID retention conservatively lasts until original 30-day life and 30 days after last receipt have both passed. Session IDs are never reused.

### Indefinite market and infrastructure

No financial reset occurs at a scenario end, packet lifetime, 200-year scan end or future orbital epoch. Existing positions and exports keep named owners and backing. Cash can only be replenished by actual earnings or contributions from the conserved pool; fees are zero in v2 and no institutional guarantee fund is invented.

Local computers/durable storage and the brief's gateway infrastructure are assumed available within admitted limits. Their real operating costs are not modeled as free financial collateral. Future operations funding would require explicit fees/contributions. Registry, destination or authority migration is quiescent: stop new obligations, resolve all affected live work, reconcile custody, acknowledge a new version, then resume. An unreachable participant prevents migration rather than authorizing a second spending authority.

## 8. Opening book and price-dependent contract

All S1 runs start at hour 0 from the same full opening book. The rising and falling runs are separate resets. Institutions start with nothing. S3 relocates one existing account with its assets under the brief's explicit rule; it does not add capital or another principal.

| Account | Home | NeoDollars | Opening shares and authority |
|---|---|---:|---|
| Alice | Earth | 150,000 | None |
| Bob | Mars | 50,000 | 3,000 Ares Habitat, Mars |
| Cara | Ceres | 100,000 | 1,000 Belt Works, Ceres |
| Dax | Neptune | 100,000 | None |
| Eve | Uranus | 50,000 | None |
| Fin | Earth | 50,000 | 1,000 Terra Fabrication, Earth |
| **Total** | **Five settlements** | **500,000** | **5,000 shares** |

### Equity examples

Alice buys 1,000 Ares shares from Bob at $100 each through Mars, or separately buys 1,000 Belt Works shares from Cara through Ceres. Alice reserves $100k from her $150k. Seller inventory starts locally, so no initial inventory transfer is omitted. The source reservation expires at hour 72 if still unpaid; the market's payment request has the earlier acceptance cutoff from Section 4. Filled payment obligations do not expire.

After the Ares purchase: Alice has $50k and 1,000 Ares shares in Earth custody; Bob has $150k and 2,000 Ares shares on Mars. After the separate Belt purchase: Alice has $50k and 1,000 Belt shares in Earth custody; Cara has $200k and no Belt shares. All other holdings stay unchanged. Buyer investment exposure is $100k if the acquired stock later becomes worthless; seller has no unsecured principal-delivery exposure under the protocol but bears provisional-match and opportunity costs.

### Capped futures: keep the arithmetic, simplify custody

The hosting exchange is Mars. There is no separate clearer. Unlike v1's remote collateral locks, **both contributions are explicitly transferred into customer escrow at the contract host before opening**. This costs funding/return packets and immobilizes collateral remotely, but removes a distributed margin-control protocol. Collateral remains the clients' beneficial property and is never exchange capital.

Fixed terms, declared before either path:

- Alice long, Cara short; contract ID and complete terms hash fixed in advance.
- Q = 2,000 NeoDollars per index point, entry strike K = 100; reference notional QK = $200,000.
- Total lifetime net payoff to long: `Q × (clip(P, 60, 140) − 100)`; short receives its negative.
- Each side's maximum possible loss is $80,000. Both must contribute that full amount to this contract's escrow. No share collateral, cross-position netting, or rehypothecation.
- Both clients send explicit authenticated opening instructions to Mars by direct/local access. Official collateral transfers do not secretly forward client orders over the backbone.
- Open only when Mars has both instructions and both credited escrow contributions. Record both encumbrances and the position atomically. Send OPENED to both homes over the backbone so they can display the authoritative position and maturity. The trade/funding service counts those messages.
- Opening acceptance deadline is hour 168 in the scenario manifest. If the position has not opened by then, Mars records a terminal unopened/return decision and returns credited or subsequently arriving tagged contributions through funded transfers. Late packets cannot open that contract after the deadline. Any unreturned contribution remains an identified funded liability until delivery home.
- Position stays open for exactly 300 hours from its **actual** opening time. Opening delays do not shorten its life below 240 hours. No early liquidation or in-place amendment in the baseline.
- Bob is the named synthetic Ares Price Index source, publishing one signed packet locally on Mars at open+60, +120, +180, +240 and +300 h. He learns the schedule by local access after opening. No new oracle institution or free remote broadcast is assumed.
- Use the +300 h observation if authenticated and received by maturity+24 h. If absent, use the latest earlier scheduled observation received by that cutoff; if none, use 100. Source, schedule, timestamp and observation ID must match. Late observations cannot rewrite a finalized payoff; conflicting source values for one observation invalidate that observation before fixing and invoke the fallback.
- Intermediate observations update informational P&L only. There are no interim cash variation payments to count again at maturity.

**One margin/default rule for both paths:** contribute maximum contractual loss before opening; keep it until final allocation. If funding is insufficient, the position does not open. Increasing size requires a new separately funded contract. There is no reliance on future prices or reachable clients, no margin-call liquidation, and no invented unfunded default fund. Operational payout delay is funded pending settlement, not a fabricated counterparty default.

At fixing, Mars atomically allocates the $160k escrow between its two owners and records two irrevocable payout exports to their homes. The total net derivative obligation is discharged on that authoritative allocation/debit record; the resulting payout claims are backed by those exports. Each home spends its result only on import. Record discharge, backed claim and local spendability separately. The receipt from each home closes that payout's delivery work.

| Relative time | Rising run | Falling run |
|---|---:|---:|
| Entry | 100 | 100 |
| +60 h | 110 | 90 |
| +120 h | 120 | 80 |
| +180 h | 130 | 70 |
| +240 h | 135 | 65 |
| +300 h | 125 | 75 |

Both paths move 35% from entry. Final net payment is +$50k to Alice in the rising run and +$50k to Cara in the falling run. The winner receives $130k **including return of its original $80k**, and the loser receives $30k. These are not $130k and $30k of trading profit.

Rising final cash: Alice $200k, Cara $50k. Falling: Alice $100k, Cara $150k. Other accounts unchanged; total remains $500k. Exposure is $80k per side; peak cash encumbrance $160k =32% of opening cash. Notional/value-settled denominator on completion is $200k, so capital efficiency is 0.8. Post-open escrow alone contributes $160k×300 =48,000,000 dollar-hours; full evidence adds funding transit, pre-open waiting, fixing delay if any, and payout transit by owner. The model must not reset the capital clock when custody moves.

**Binding constraint:** Q=2,501 requires $100,040 per side; Cara only has $100k. Reject/suspend before opening. Q=2,500 is the theoretical funding boundary before other locks; Q=4,000 requires $160k each and also fails Alice's limit. Contract prices outside [60,140] bind the payoff cap, a disclosed basis risk rather than an unfunded debt.

**Oracle risk:** the supplied price scripts are synthetic contractual inputs; the named source is not a claim of independent or economically manipulation-resistant price discovery. Authentication solves attribution, not source honesty. Real index governance is a deployment extension.

### Financial-product extensions

Capped options can use maximum-payout escrow and separately funded premiums. Covered calls require exclusively reserved shares and exercise/delivery rules. Loans and bonds create claims and liabilities but not free cash; guaranteed principal/interest needs specified backing, and volatile collateral does not guarantee cash recovery. Borrowed-stock shorts need explicit borrow/return/buy-in rules; current short exposure is the bounded futures short. A new currency requires encumbered backing and a matching liability. None is counted as an implemented second product instead of the demonstrated equity/futures pair.

## 9. Transport and packet accounting

### Preserve the brief's transport exactly

Application simplification does not remove hop receipts, transport acknowledgments, route limits, timers, packet lifetime, quotas, FIFO or maintenance.

- A new session has SYN/SYN-ACK/final ACK. Initiator may send data after queuing final ACK; receiver waits for that ACK before application release.
- Hop receipt is queued on the reverse link on reception; first data copy forwards after relay processing. Duplicate data triggers another receipt but no duplicate forwarding. Hop receipts are one-shot and are not themselves receipted.
- Every launch incurs serialization and actual moving-receiver loss. R_h starts at emission, is recalculated for each of at most four launches, and covers twice flight plus 60 min. Late receipt cancels only unlaunched retries.
- Endpoint R_e starts on enqueue, including behind a closure. At most four attempts for SYN, SYN-ACK and data; final ACK has no timer of its own. Repeated SYN-ACK can trigger another final ACK. Retry gets a new network packet ID while preserving session byte position, financial ID and original packet lifetime. Older unlaunched endpoint copy is removed; endpoint/hop retries can overlap.
- T0 is sequential empty-queue route delay including serialization and relay processing; evaluate light time even for a blocked link when calculating this timer. It does not predict a delivery deadline.
- Known solar/maintenance closure waits; a flight overlapping scheduled maintenance is not launched. A hidden incident fails launches based on emission time. Already emitted packets are not retroactively lost when an incident begins.
- Sessions expire after seven days without receipt; resets kill their volatile state. Financial records/outboxes and packet-ID records survive. Dead-session arrivals are ignored. New sessions and application queries/resubmissions count against quota.
- All launch/receipt/retry totals count toward communication efficiency even when quota-exempt. Link capacity is separate from origination quota.

### Compact fixed-width records

Use a 16-byte batch header (version 2, record count 2, sender principal 4, batch sequence 8) plus a 64-byte record envelope (type 2, flags 2, body length 4, request ID 16, object ID 16, expected version 8, event sequence 8, logical time 8). Integers are fixed-width and uncompressed. Bounds must be checked before financial admission. A batch contains records for one peer; each record fits in a packet, with no record fragmentation in the baseline.

| Record | Fixed maximum body bytes | Envelope + body | Maximum records per 960-byte payload |
|---|---:|---:|---:|
| ORDER | 80 | 144 | 6 |
| PAY_REQUEST | 160 | 224 | 4 |
| PAYMENT | 96 | 160 | 5 |
| DELIVERY | 120 | 184 | 5 |
| RECEIVED | 56 | 120 | 7 |
| NO_PAYMENT / STATUS / VOID_REQUEST | 64 | 128 | 7 |
| TRANSFER | 80 | 144 | 6 |
| PRICE observation | 136 | 200 | 4 |
| CONTRACT_INSTRUCTION | 192 | 256 | 3 |
| OPENED | 64 | 128 | 7 |

For ORDER, the envelope flags identify buy/standing-sell instruction and its expected-version field identifies the registry version; these are immutable authenticated terms. The demonstrated buyer model fixes side=buy and registry version=2. ORDER body: owner/home/market/destination IDs 4 bytes each; order and reservation IDs 16 each; asset, quantity, limit price and expiry 8 each. PAY_REQUEST adds transaction ID 16, seller/home IDs 4 each, execution price 8, acceptance cutoff 8, delivery-promise digest 32, authority epoch 8. PAYMENT uses transaction ID 16, request digest 32, export ID 16, source/destination IDs 4 each, amount 8, owner/beneficiary IDs 4 each, decision time 8. DELIVERY uses transaction ID 16, request digest 32, export ID 16, custody lot 16, asset and quantity 8 each, source/destination/beneficiary/epoch IDs 4 each, ledger sequence 8. RECEIVED is object ID 16, digest 32, sequence 8. Control body is target ID 16, digest 32, state/reason 8, time 8.

TRANSFER body is export ID 16, asset 8, amount 8, owner/source/destination/beneficiary IDs 4 each, custody reference 16, authority epoch 8, reason 8. PRICE body comprises oracle ID 4, index ID 8, observation ID 16, contract ID 16, observation time 8, price 8, authority epoch 4, sequence 8 and signature 64: 136 bytes. Operator identity authentication is the brief's baseline assumption; these estimates do not pretend to implement a Byzantine-proof signature chain. Full binary encoding is a Milestone 2 implementation task; current traces are readable logs.

Contract terms are fixed-schema, versioned and hash-bound. CONTRACT_INSTRUCTION body: contract ID 16; canonical terms hash 32; two principal and two home IDs 16; host and oracle IDs 8; collateral and index IDs 16; Q, strike, lower cap, upper cap and per-side margin 40; opening deadline, duration, observation interval and fixing grace 32; observation count and rule version 8; reserved-zero bytes 24. Total 192. Both client instructions contain the same terms; authenticated sender determines the long or short role. Units and rounding are fixed by rule version (integer cash cents, integer index points for the demonstrated contract). OPENED body: contract ID 16, terms hash 32, actual opening time 8, maturity time 8. Funding transfers bind the contract through their custody reference and reason. The rule version specifies the fallback in Section 8. Admission requires exact terms and observations to fit the packet budget; larger optional contracts require explicitly counted packets or rejection. Encoding and round-trip tests remain implementation work; an arbitrary legal document is not assumed to fit an ORDER record.

Batch independent records for at most 60 s; payment/delivery recovery may flush immediately. A lost batch is a shared loss event for all its records. Do not claim batching savings in traces that do not actually batch. Reusing an existing live session saves a handshake; do not silently pre-establish it for free.

### Why the new example is 45 transmissions

For a two-hop route, each application packet generates two data launches, two hop receipts, two endpoint-ACK launches and two receipts for those ACK launches: eight physical transmissions. Each new three-message handshake generates twelve transmissions and one charged SYN. There are four application messages in the completed spot exchange: PAY_REQUEST, PAYMENT, DELIVERY, RECEIVED.

| Component | Physical transmissions | Backbone originations |
|---|---:|---:|
| Cold session handshake | 12 | 1 |
| Four application records, unbatched | 32 | 4 |
| One buyer direct ORDER | 1 | 0 |
| **Total** | **45** | **5** |

The direct ORDER separately consumes one client direct token. With the market initiating the session, it creates three backbone originations (SYN, PAY_REQUEST, DELIVERY); the buyer home creates two (PAYMENT, RECEIVED). Five is 0.833% of the global 600 allowance, but each institution also obeys its sub-budget. The measured packet efficiency is 45 transmissions per completed trade, not five. With a genuinely existing session, the isolated marginal count would be 33 and four; retries and queries add traffic.

RECEIVED is retained rather than hidden as a free deferred message: it establishes destination application processing and permits bounded sender recovery records. Removing it would require an explicitly counted later status/receipt scheme. A transport ACK alone does not confirm application acceptance.

### Probability accounting

Every direct copy has success `exp(−0.08d)` if its launch and deadline arrival are feasible. A blocked/forced-loss copy has zero success. For predetermined independent copies of one required message, success is `1−product(failure_j)`; adaptively timed messages, common closures, batches and quota constraints need their real dependency graph. The current traces each contain one required direct order and no optional remote client ACK.

For a hop under open, uncongested conditions, per-attempt no-confirmation probability is `q=1−(1−p_forward)(1−p_receipt)`. Product of four q values is an abandonment upper bound allowing late receipts to suppress retries. Product of four forward-loss probabilities instead measures all data launches failing. Compute each attempt and reverse receipt from its own geometry. These are not end-to-end session probabilities, and under outages/receipt congestion they do not apply unchanged.

The retained hop calculations at epoch give Earth→A forward loss about 4.411%, abandonment upper bound about 0.00553%; Neptune→A forward loss about 42.716%, abandonment upper bound about 20.381%. The outer-system packet count can grow substantially beyond the no-loss trace. An unconditional deadline does not exist.

## 10. Executed evidence and worked examples

### Revised spot traces

`trace_v2.py` runs the authoritative v2 financial model through a conditional packet simulator with moving receivers, serialization, pinned handshakes, hop receipts and endpoint data ACKs. A session starts **after the market receives the buyer's order**, not before hour 0 or with free anticipatory setup. The simulator raises if a known closure would require waiting; none occurs on the reported routes. General lossy transport, exact closure waiting and reset/session recovery are still Milestone 2 work.

Each run resets to the original opening book; Jupiter/Neptune cases relocate Alice under S3. All use exact quantities, $100k funding, and the same local-spendability requirement.

| Case | Market | Conditional completion, hours | Required direct-order success | Total transmissions | Backbone originations |
|---|---|---:|---:|---:|---:|
| Alice Earth, Bob Mars | Mars | 3.067461 | 0.871073 | 45 | 5 |
| Alice Earth, Cara Ceres | Ceres | 3.164518 | 0.802497 | 45 | 5 |
| Alice relocated Jupiter, Bob Mars | Mars | 3.946131 | 0.699925 | 45 | 5 |
| Alice relocated Neptune, Bob Mars | Mars | 24.680839 | 0.093640 | 45 | 5 |

These probabilities are for the required direct order, not entire-trade success by those times. The timing also conditions on no random backbone loss. If the order fails, the operation remains incomplete; an unpaid source reservation returns to available cash on local cancellation/expiry. If payment was recorded, expiry does not refund it.

The original Earth–Mars example was 4.524640 h, 69 transmissions, eight originations. Version 2 removes 24 transmissions (34.8%) and three originations (37.5%). The original Earth–Ceres-via-Mars example was 4.993504 h, 149 transmissions, seventeen originations; v2 removes 104 transmissions (69.8%) and twelve originations (70.6%). These are worked-example comparisons, not universal throughput claims. Earlier examples started some sessions earlier; the new timing does not assume that advantage.

### Earth–Mars financial timeline

| Time, hours | Actor / event | State |
|---:|---|---|
| 0.000278 | Local reserve and standing sell order | Alice $100k reserved; Bob 1,000 shares committed to sell inventory |
| 0.239999 | Mars receives direct ORDER | Provisional match; shares promised; starts session and PAY_REQUEST |
| 1.936177 | Earth accepts PAY_REQUEST | Cash debited/exported; reservation consumed; share-delivery claim backed by Mars's promised stock |
| 2.501872 | Mars receives PAYMENT | Cash imported/seller credited and shares debited/exported atomically; seller proceeds spendable |
| **3.067461** | Earth receives DELIVERY | Shares credited locally once; **trade complete** |
| 3.633122 | Mars receives RECEIVED | Market knows home delivery completed |

Peak encumbrance remains $100k and 1,000 Ares shares: no savings come from weaker funding. Dollar-hours fall to **250,159.415** and Ares share-hours to **3,067.183**, counting from the local lock through the corresponding spendable result, including in-transit backing. Cash utilization 20%, trade value $100k, capital efficiency 1.0. The futures scenario supplies the separate ≥25% scale condition.

Earth–Ceres seller cash becomes spendable at 2.607969 h, buyer shares at 3.164518 h, and Ceres knows completion at 3.721109 h. No Mars clearing messages occur. Dollar-hours are 260,769.084; Belt share-hours 3,164.240.

`v2_*_balances.csv` audits the changing buyer balance, seller proceeds, locked/in-transit cash and shares alongside unchanged opening assets at each financial transition. No master copy or claim is added as extra money or stock. Full standalone scenario appendix rows will name all owners and locations; these compact audit files are not a substitute for that appendix.

### Adversarial application checks

The current test suite executes **27 tests** and explores **19 reachable financial states / 190 attempted transitions** in a bounded one-trade message abstraction. It covers:

- conflicting reservations competing for the same available cash;
- one reservation referenced by multiple order/transaction IDs;
- wrong client, market, order terms, amount, source identity and replay payload;
- cancellation, void and expiry before versus after payment;
- price improvement without reuse of the spent reservation;
- partial-quantity requests rejected rather than silently supported;
- market timeout while PAYMENT may be lost;
- reset/retry after 30-day packet lifetime without forgetting the payment;
- duplicate delivery/receipt without another stock credit;
- integer/overflow bounds;
- capped derivative allocation in both directions and beyond price caps.

These tests use the application state transitions used by the new traces. The abstraction treats loss as no delivery and reset as preservation of durable financial records; it is **not** an exhaustive proof of production code, full transport or malicious-operator behavior. The isolated-hop forced-loss probes from Milestone 1 remain useful transport evidence: four Earth→A attempts can all fail inside a six-hour incident, and four Neptune→A attempts can run out before a 72-hour isolation ends. They are not full S2 financial recovery times.

### Retained geometry and long-horizon evidence

Orbital work is unchanged by the financial redesign:

- Maximum coordinate error against rounded epoch table: 4.679×10⁻⁷ AU, below 10⁻⁵ AU.
- Supplied-period return and radius-bound checks pass. Moving-receiver residuals are tested at negative time, hour 300 and 200 years.
- Earth→Mars at emission t=0: 860.995951 s moving flight vs 860.951655 s frozen, +44.297 ms. Reverse emitted at t=0: 860.875366 s, −76.289 ms from frozen. Actual trace replies use later emission geometry.
- Maintenance check correctly excludes Neptune→B emitted at t=0 because the flight overlaps the hour-2 maintenance start.
- 200-year hourly scan: 1,753,201 epochs, all 38 directed links, moving-receiver solar clearance, no repetition of one-time maintenance.
- Refined Mercury→A open-to-blocked emission boundary: original [7,135,200, 7,138,800] s bracket to [7,138,362.320137, 7,138,362.320995] s, under 1 ms. Already emitted photons are evaluated by their own path, not retroactively erased by a later boundary.
- Chosen difficult screening epoch: hour 993,506, approximately 113.34 years. Exact Neptune→A→B→Mars forward delay 314.876465 min, reverse 314.849888 min; first-hop loss about 45.72%.

An hourly grid detects continuous closures longer than an hour but can miss shorter/grazing closures. The long-scan route screen evaluates links at a common epoch, so it is not exact sequential forwarding near boundaries. Its sampled connectivity and extrema are not proof of perpetual access. Retain **E4 Tier 2 candidate** status; Tier 3 requires exact route/window refinement for the current service graph. The known orbital model is an indefinite mathematical challenge model, not an accurate real solar-system ephemeris for eternity.

Hour-0 / hour-300 best routes to the Mars equity/contract market remain:

| Settlement | Route at both hours | Delay min at 0 / 300 | Sampled next-24h route launch availability |
|---|---|---:|---|
| Mercury | Mercury–A–Mars | 42.368 / 42.032 | 100% / 100% |
| Venus | Venus–A–Mars | 36.911 / 35.923 | 100% / 100% |
| Earth | Earth–A–Mars | 33.912 / 33.444 | 100% / 100% |
| Mars | Internal | 0 / 0 | 100% / 100% |
| Ceres | Ceres–A–Mars | 29.713 / 30.500 | 100% / 100% |
| Jupiter | Jupiter–B–Mars | 39.905 / 39.233 | 100% / 100% |
| Saturn | Saturn–A–Mars | 75.766 / 77.124 | 100% / 100% |
| Uranus | Uranus–A–Mars | 154.611 / 154.988 | 100% / 100% |
| Neptune | Neptune–A–Mars | 246.846 / 248.330 | 100% / 100% |

Availability here samples every minute and means all links of the selected route can launch at that sampled time, not session delivery probability. S3 must include the actual market, funding, inventory and payout authorities for each offered product, including reverse routes. Mars is best, Jupiter median and Neptune worst by this Mars-route ranking. The all-local Mars stock trade is an atomic local operation after both instructions arrive (analytical 1 s for simultaneous initial local instructions); the median/worst remote v2 traces above are executed comparisons. Client knowledge follows local notification and is distinct from local balance availability.

## 11. Scenario and evidence handoff

### S1

Use separate resets unless explicitly running simultaneous workloads:

1. Earth–Mars stock trade, and the Earth–Ceres stock trade as a contrasting asset market. End initially hour 48; retain named funded pending states if loss extends settlement.
2. Alice/Cara capped futures rising run, starting hour 0, actual escrow transfers and direct instructions, open+300 h maturity. Initial end hour 600; state every remaining funded export if not complete.
3. Exact same opening book, funding/margin rules and algorithm for falling run; only published path changes.
4. Funding boundary Q=2,500 and rejection Q=2,501 (and larger Q=4,000). No position opens on incomplete margin. Report any contributed assets' funded return state.
5. Comparable local/median/worst access reruns with one existing account relocated under S3, never new wealth.

At least one completed derivative scenario must demonstrate simultaneous $160k encumbrance; do not substitute a rejected opening for the scale condition. Report every side's exposure, peak encumbrance by asset, asset-hours, completed notional/trade value and packet efficiency. Separate gross collateral returns from net payoff.

### S2

The main current candidate remains Mars isolation around maturity/payout: the contract and synthetic source are there, and all $160k is escrowed there. Local fixing still works during gateway isolation, but payout exports cannot reach homes. This is a real concentration cost of simpler custody. Another candidate is isolating the payment-source gateway immediately after a spot cash debit, stranding promised inventory; S2 itself must include the price-dependent product.

Search all allowed incident kinds, eligible targets and transition/emission-adjacent start times plus an hourly grid. Rank by loss of financial service for accepted obligations, then extra asset-hours and unfinished operations. Do not select the incident using a privileged actor that knows the schedule. A six-hour forced-loss event, reset and 72-hour isolation need actual full-session comparison; the current probes do not prove a global worst case.

Repeat the selected run at the same absolute incident time with scheduled maintenance removed and geometry unchanged. Report zero difference if maintenance does not affect its paths. For a same-funding/same-guarantee sensitivity, use one versus several explicitly budgeted direct ORDER copies, or prior funding verification versus on-demand verification. Include all extra setup, observations, query responses and resubmissions. Restoration means an affected financial service can complete again, not that a packet arrived.

### E1–E5 status

| Evidence | Available now | Still required for Milestone 2 |
|---|---|---|
| E1 | Frozen propagation, epoch/period/radius/residual checks; moving-receiver examples | Compact standalone calculations and exact selected return paths |
| E2 | Four v2 conditional spot traces with all transport transmissions, direct probabilities, quota counts; hop bounds | Full lossy endpoint/queue/reset/closure behavior; derivative and stress traffic/deadline calculations |
| E3 | Current financial model, replay/double-spend/cancel checks; spot audits; capped payout checks | Full named-account event audit for both derivative paths, escrow transfers and payout asset-hours |
| E4 | 200-year link scan and one refined boundary; limits stated | Exact sequential route/window extrema for all current services if claiming Tier 3 |
| E5 | +1/+10/+100 route/access calculations and a difficult epoch | Rerun current protocol and both price paths with shifted observations/maturity, original phase retained, no replayed original maintenance/incident |

Symmetric payoff funding does not imply symmetric network completion: the winner changes homes and gross return amounts change. Do not skip the second difficult-epoch price run merely because the formula is symmetric.

S3 must be updated for Earth, Mars and Ceres asset markets and contract funding/payout routes, rather than interpreted as access to the obsolete two-clearer partition. Old `placement_screen.json` remains a historical geography experiment only. Existing Mars long-scan geometry remains useful to the demonstrated futures; it does not establish every new service guarantee.

## 12. Deployment and limits

Two numerical real-deployment effects remain explicitly outside the common baseline:

1. NASA's Earth radius 6378.137 km and sidereal rotation 23.9345 h imply equatorial surface speed about 0.4651 km/s. A single equatorial ground station viewing a roughly equatorial distant target with zero elevation mask can have approximately **11.97 h below-horizon intervals**. The brief folds these effects into always-available one-second local access. A real system would need additional visibility support or tolerate longer waits. Exclusive backing remains safe if waits are explicit; baseline latency promises would change. [NASA Earth Fact Sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html).
2. An illustrative 30 km/s radial relative speed at a 32 GHz carrier gives Doppler shift about **3.20 MHz** using fv/c. The speed is an assumption of Earth's orbital-velocity scale, not a calculated Earth–Mars radial velocity. ESA documents 32 GHz use and Doppler tracking. Real modems must track that shift or incur additional loss; the conservative financial invariants tolerate loss/delay, not arbitrary undetected corruption or forged identities. [NASA Earth Fact Sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html), [ESA Cebreros](https://www.esa.int/Enabling_Support/Operations/ESA_Ground_Stations/Cebreros_-_DSA_2), [ESA Delta-DOR](https://www.esa.int/Enabling_Support/Operations/Keeping_track_of_spacecraft_with_Delta-DOR).

No unlisted network links, local satellite orbits, free broadcasting, legal enforcement, credit advance or future endowment is introduced. No guarantee depends on all-time uninterrupted connectivity or free operator financial resources.

The external settlement analogy is delivery-versus-payment: recipients should not obtain spendable results without corresponding recorded asset debits. The bilateral protocol implements that condition using each authority's durable financial evidence, rather than an independently chartered clearinghouse. [CPMI–IOSCO PFMI overview](https://www.bis.org/committees/cpmi/pfmi/overview). Durable commitments can still block when parties are unreachable; eliminating redundant rounds does not create a nonblocking distributed system. [Gray and Lamport, Consensus on Transaction Commit](https://arxiv.org/abs/cs/0408036).

## 13. Ready-for-Milestone-2 decisions

The current baseline is settled: local market/settlement authority, order-bound single-use reservations, exact-quantity orders, on-demand payment verification, durable payment/delivery/receipt, explicit remote inventory/proceeds transfers, host-funded capped contracts, and finite distributed quotas. These are implementation choices, not outstanding questions for the user.

The remaining work is execution and evidence: complete the brief's lossy transport model; simulate all escrow and payout legs; measure provisional-match abuse and outage recovery; refine long-horizon service windows; and produce the paper/appendix. If those tests expose a counterexample, revise the rules and rerun affected evidence before claiming correctness. A simpler state machine is not a claim that every production edge case has already been proven.
