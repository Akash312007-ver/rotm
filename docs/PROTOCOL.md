# ROTM Protocol Design Document

## 1. Problem Statement

Digital payments in India (UPI and similar systems) assume continuous
connectivity to a central authority that can atomically check and update
account balances. When connectivity is unavailable -- natural disasters,
rural network gaps, deliberate infrastructure attacks on the power grid
or telecom towers -- these systems stop working entirely, even though the
transacting parties are physically present and willing.

ROTM asks: can two devices exchange value with cryptographic integrity
when neither can reach a central authority, and if perfect security isn't
possible, what is the best *achievable* guarantee?

## 2. Threat Model

We assume:
- Devices can be temporarily or permanently offline (no connectivity to
  any server or the wider mesh) for arbitrary periods.
- A sender may act maliciously and attempt to spend the same funds twice
  by presenting two validly-signed transactions to two different
  recipients before either transaction reaches a common ledger.
- Private keys are not compromised (key management/device security is
  out of scope for this protocol layer).
- The mesh network (device-to-device relay) may be sparse -- two devices
  involved in a double-spend attempt may not meet directly for an
  arbitrary number of hops/time.

We explicitly do NOT defend against:
- Compromised device/stolen private key (a separate, standard problem --
  mitigated by device-level auth, out of scope here)
- Sybil attacks on the mesh relay layer (a future work item, noted in
  Section 6)

## 3. Impossibility Result (why this matters for the paper)

**Claim:** No protocol relying solely on offline, unsynchronized devices
can *prevent* double-spending with certainty, for the same reason no
distributed system can achieve strong consistency without communication
(this is a direct consequence of the CAP theorem's partition-tolerance
trade-off, applied to a payment ledger).

This is not a flaw in ROTM's design -- it is a fundamental limit of the
problem as stated. Any system claiming to "solve" offline double-spend
prevention is either making an assumption we don't (e.g., trusted hardware
enclaves, out of scope for a phone-based system) or is incorrect.

**What IS achievable, and what ROTM targets:**
1. Bound the maximum damage any single compromised sender can cause before
   detection (Section 4.1)
2. Guarantee eventual, deterministic detection once transaction histories
   merge (Section 4.2), with measurable detection latency
3. Provide a real-time, local risk signal to reduce the *likelihood* of
   accepting a risky transaction, without claiming certainty (Section 4.3)

## 4. Protocol Design

### 4.1 Bounded Offline Exposure

Each wallet enforces a hard `offline_cap` -- the maximum cumulative amount
it will allow to be spent since the last confirmed sync with any ledger
(a server, or another device acting as a relay point with recent server
contact). This cap resets only on confirmed sync.

This transforms an unbounded risk ("attacker could double-spend
unlimited amounts") into a bounded, quantifiable one ("attacker can
double-spend at most `offline_cap` per sync cycle") -- which is the
correct framing for a risk-management system, mirroring how physical cash
and existing offline payment pilots (e.g., RBI's e-Rupee offline pilots)
handle exactly this trade-off.

**Implementation:** `core/transaction.py`, `Wallet.offline_cap_paise`.

### 4.2 Deterministic Conflict Detection

Every transaction is signed with Ed25519 and carries a strictly-increasing
per-sender nonce. A ledger detects a conflict under two conditions:

1. **Nonce collision**: two distinct, validly-signed transactions from the
   same sender share the same nonce (direct evidence of a forked
   transaction history).
2. **Balance exceeded**: cumulative committed transactions from a sender
   exceed their last known-confirmed balance.

Detection happens automatically the moment two ledgers merge (device
meets device, or device reconnects to a server) -- no manual reconciliation
step is required. This is proven correct in `tests/test_core.py::
test_double_spend_detected_on_ledger_merge`.

**Reconciliation policy:** first-committed-transaction-wins. The
transaction accepted earliest (by the merging ledger's local clock) is
honored; the conflicting transaction is rejected and its recipient is
notified their incoming payment was invalid. The sender's offline
privileges are throttled (halved) for each detected conflict
(`sync/ledger.py::_throttle_sender`), disincentivizing repeated attempts.

**Implementation:** `sync/ledger.py`.

### 4.3 Local LLM Advisory Risk Scoring

A small on-device language model (Gemma 3 4B or similar, served locally
via LM Studio/Ollama) scores each transaction against the sender's recent
behavioral profile, blended with deterministic heuristic features
(z-score of amount vs. sender history, new-recipient flag, proximity to
offline cap). This never blocks a transaction unilaterally -- it attaches
a `risk_score` in [0,1] as metadata for the recipient's UI and for
prioritizing investigation once transactions reach a ledger.

This design choice is deliberate: giving a small, locally-run model
unilateral blocking authority over a monetary transaction, with no
recourse or oversight, is not something we consider responsible given the
model's size and lack of ground truth beyond the sender's local history.

**Implementation:** `detection/risk_scorer.py`.

## 5. Evaluation Methodology

Because acquiring dozens of physical test phones is impractical for a
solo/small-team project, we use a discrete-event mesh simulator
(`sync/mesh_simulator.py`) modeling N nodes, a configurable fraction
acting maliciously, and randomized pairwise "meetings" simulating
Bluetooth/WiFi Direct range encounters. This is standard practice in
distributed systems research when physical deployment at scale isn't
feasible for initial evaluation (see e.g. evaluation methodology in
DTN/opportunistic-networking literature).

**Metrics collected:**
- **Conflict rate**: fraction of malicious double-spend attempts that are
  eventually detected vs. total transaction attempts
- **Detection latency**: number of device-hops between the two halves of
  a double-spend attempt and the moment the conflict is detected
- **Cap sensitivity**: how `offline_cap` size trades off against exposure
  (larger cap = more usability, more potential damage per undetected
  window)

Results from an initial run (20 nodes, 2 malicious, 40-50 rounds) are in
`results/` -- see `week1_llm_risk_scoring.md` for the LLM scoring results
and the console output from `sync/mesh_simulator.py` for the cap
sensitivity sweep.

## 6. Known Limitations / Future Work

- **Sybil resistance at the mesh relay layer** is not addressed -- a
  malicious node controlling many mesh identities could delay conflict
  detection by selectively refusing to relay/merge. Mitigations
  (reputation scoring, relay diversity requirements) are future work.
- **Real device-to-device transport** (actual Bluetooth/WiFi Direct) is
  not yet implemented; the simulator models this abstractly.
- **LLM risk scoring is advisory-only by design** (Section 4.3) -- this
  is a deliberate scope limitation, not an oversight, but should be
  stated explicitly in any paper to preempt reviewer questions about why
  the LLM doesn't have blocking authority.
- **Throttle recovery mechanics** (how a throttled sender's offline
  privileges restore over time after good behavior) are implemented
  minimally and would benefit from a more principled design before
  production use.

## 7. Related Work Context (for paper positioning)

This work sits between two existing bodies of work:
- **Central-bank offline digital currency pilots** (e.g., RBI's e-Rupee
  offline trials, various CBDC offline-payment research) which address
  the same bounded-exposure problem but typically assume dedicated secure
  hardware elements, which most consumer Android/iOS devices don't expose
  to third-party apps.
- **Delay-tolerant networking (DTN) / opportunistic networking research**,
  which addresses the mesh-relay and eventual-consistency aspects but
  historically hasn't been applied specifically to payment integrity with
  a local ML-based risk layer.

ROTM's contribution is combining bounded-exposure offline payments with
a fully local (no-cloud) ML risk-scoring layer, evaluated via mesh
simulation -- a combination we have not found precedented in existing
literature as of this writing (worth a proper literature search before
final submission, this is a starting position not a verified novelty claim).
