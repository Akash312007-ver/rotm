---------------------------- MODULE ROTM ----------------------------
(***************************************************************************)
(* ROTM Double-Spend Detection Protocol -- Formal Specification            *)
(*                                                                         *)
(* Plain-English summary for readers new to TLA+:                        *)
(*                                                                         *)
(* This spec models the CORE safety claim of ROTM (see PROTOCOL.md        *)
(* Section 4.2): "no ledger, after any sequence of merges, ever believes  *)
(* it has committed more spend for a sender than that sender's known      *)
(* balance." We model a small number of wallets and ledgers, let them     *)
(* take actions in any possible order (submit a transaction, attempt a    *)
(* double-spend, merge two ledgers), and ask TLC to exhaustively check    *)
(* every reachable state for a violation of that claim.                  *)
(*                                                                         *)
(* We deliberately do NOT model cryptographic signatures (we assume they  *)
(* cannot be forged -- that's a separate, well-studied problem), network  *)
(* timing, or Sybil-resistance (Section 8, a separate layer). This keeps  *)
(* the model small enough to check exhaustively while still capturing    *)
(* the exact logic in sync/ledger.py's submit() and merge() functions.    *)
(***************************************************************************)

EXTENDS Integers, FiniteSets, Sequences, TLC

CONSTANTS
    Wallets,        \* Set of wallet identities, e.g. {"W1", "W2"}
    Ledgers,        \* Set of ledger identities, e.g. {"L1", "L2"}
    MaxNonce,        \* Upper bound on nonce values (keeps state space finite)
    InitialBalance,  \* Every wallet's known balance at every ledger, at start
    Amounts          \* Small discrete set of transaction amounts to try (keeps state space finite)

VARIABLES
    walletNonce,        \* walletNonce[w] = next nonce this wallet will use
    ledgerEntries,       \* ledgerEntries[l] = set of committed txn records at ledger l
    ledgerNoncesSeen,    \* ledgerNoncesSeen[l][w] = set of nonces already committed for w at l
    ledgerCommitted,     \* ledgerCommitted[l][w] = total paise committed for w at l
    ledgerKnownBalance   \* ledgerKnownBalance[l][w] = w's balance as known by l

vars == <<walletNonce, ledgerEntries, ledgerNoncesSeen, ledgerCommitted, ledgerKnownBalance>>

(***************************************************************************)
(* A transaction record: who sent it, what nonce, how much, to whom.      *)
(* We model "amount" abstractly as any value from 1 to InitialBalance --  *)
(* the actual number doesn't matter for the safety property, only that   *)
(* committed spend is tracked correctly against it.                      *)
(***************************************************************************)
Txn == [sender: Wallets, nonce: 0..MaxNonce, amount: Amounts, recipient: Wallets]

TypeInvariant ==
    /\ walletNonce \in [Wallets -> 0..MaxNonce]
    /\ ledgerEntries \in [Ledgers -> SUBSET Txn]
    /\ ledgerNoncesSeen \in [Ledgers -> [Wallets -> SUBSET (0..MaxNonce)]]
    /\ ledgerCommitted \in [Ledgers -> [Wallets -> Nat]]
    /\ ledgerKnownBalance \in [Ledgers -> [Wallets -> Nat]]

(***************************************************************************)
(* Init: every wallet starts at nonce 0. Every ledger starts empty, with  *)
(* every wallet's known balance set to InitialBalance (mirrors a fresh    *)
(* sync/ledger.py Ledger() with set_known_balance() called for everyone). *)
(***************************************************************************)
Init ==
    /\ walletNonce = [w \in Wallets |-> 0]
    /\ ledgerEntries = [l \in Ledgers |-> {}]
    /\ ledgerNoncesSeen = [l \in Ledgers |-> [w \in Wallets |-> {}]]
    /\ ledgerCommitted = [l \in Ledgers |-> [w \in Wallets |-> 0]]
    /\ ledgerKnownBalance = [l \in Ledgers |-> [w \in Wallets |-> InitialBalance]]

(***************************************************************************)
(* SubmitTxn(l, txn): the core logic of sync/ledger.py's submit(). A      *)
(* transaction is accepted at ledger l only if (a) its nonce hasn't been  *)
(* seen before at l for that sender, AND (b) accepting it wouldn't push   *)
(* committed spend past known balance. Otherwise it's silently rejected   *)
(* (modeled as: state doesn't change -- the "conflict" bookkeeping in the *)
(* real code doesn't affect the safety invariant we're checking here).    *)
(***************************************************************************)
SubmitTxn(l, txn) ==
    /\ txn \notin ledgerEntries[l]
    /\ IF  \/ txn.nonce \in ledgerNoncesSeen[l][txn.sender]
          \/ ledgerCommitted[l][txn.sender] + txn.amount > ledgerKnownBalance[l][txn.sender]
       THEN UNCHANGED <<ledgerEntries, ledgerNoncesSeen, ledgerCommitted>>  \* rejected
       ELSE
            /\ ledgerEntries' = [ledgerEntries EXCEPT ![l] = @ \cup {txn}]
            /\ ledgerNoncesSeen' = [ledgerNoncesSeen EXCEPT ![l][txn.sender] = @ \cup {txn.nonce}]
            /\ ledgerCommitted' = [ledgerCommitted EXCEPT ![l][txn.sender] = @ + txn.amount]

(***************************************************************************)
(* CreateAndSubmit(w, l, amount, recipient): a wallet creates a NEW txn   *)
(* using its next nonce, and submits it directly to one ledger. This      *)
(* models normal, honest usage: create_transaction() then submit() in     *)
(* the real code. The wallet's own nonce always advances (mirrors        *)
(* Wallet.create_transaction incrementing self.nonce unconditionally --   *)
(* the real code trusts the sender's own client, which is exactly what   *)
(* makes a malicious client's double-spend possible in the first place). *)
(***************************************************************************)
CreateAndSubmit(w, l, amount, recipient) ==
    /\ walletNonce[w] < MaxNonce
    /\ LET txn == [sender |-> w, nonce |-> walletNonce[w], amount |-> amount, recipient |-> recipient]
       IN SubmitTxn(l, txn)
    /\ walletNonce' = [walletNonce EXCEPT ![w] = @ + 1]
    /\ UNCHANGED ledgerKnownBalance

(***************************************************************************)
(* MaliciousDoubleSpend(w, l, amount, recipient): models exactly the      *)
(* attack scenario in PROTOCOL.md Section 3 -- a malicious wallet REUSES  *)
(* a nonce it already used (does NOT advance walletNonce), and submits a  *)
(* new, different transaction with that same nonce to a (possibly        *)
(* different) ledger. This is the direct analogue of the "reset nonce,   *)
(* create dupe_txn" step in sync/mesh_simulator.py's attack simulation.  *)
(***************************************************************************)
MaliciousDoubleSpend(w, l, reusedNonce, amount, recipient) ==
    /\ reusedNonce < walletNonce[w]  \* must be a nonce already used at least once
    /\ LET txn == [sender |-> w, nonce |-> reusedNonce, amount |-> amount, recipient |-> recipient]
       IN SubmitTxn(l, txn)
    /\ UNCHANGED <<walletNonce, ledgerKnownBalance>>

(***************************************************************************)
(* MergeLedgers(l1, l2): models sync/ledger.py's merge(). l1 absorbs      *)
(* every entry currently in l2 by re-running SubmitTxn for each one --    *)
(* exactly matching the real merge() implementation, which is what        *)
(* actually catches a double-spend: the conflicting transaction fails    *)
(* the nonce-seen check the moment the two histories combine.            *)
(***************************************************************************)
MergeOneTxn(l1, l2, txn) ==
    IF txn \in ledgerEntries[l1]
    THEN UNCHANGED <<ledgerEntries, ledgerNoncesSeen, ledgerCommitted>>
    ELSE SubmitTxn(l1, txn)

MergeLedgers(l1, l2) ==
    \E txn \in ledgerEntries[l2]:
        /\ MergeOneTxn(l1, l2, txn)
        /\ UNCHANGED <<walletNonce, ledgerKnownBalance>>

(***************************************************************************)
(* Next: at each step, either a wallet honestly transacts, a malicious    *)
(* wallet attempts a double-spend, or two ledgers merge one entry. TLC    *)
(* explores every possible choice and ordering of these actions.         *)
(***************************************************************************)
Next ==
    \/ \E w \in Wallets, l \in Ledgers, amt \in Amounts, r \in Wallets:
         CreateAndSubmit(w, l, amt, r)
    \/ \E w \in Wallets, l \in Ledgers, n \in 0..MaxNonce, amt \in Amounts, r \in Wallets:
         MaliciousDoubleSpend(w, l, n, amt, r)
    \/ \E l1, l2 \in Ledgers: l1 /= l2 /\ MergeLedgers(l1, l2)

Spec == Init /\ [][Next]_vars

(***************************************************************************)
(* SAFETY INVARIANT -- the property this whole spec exists to check.      *)
(*                                                                         *)
(* "No ledger ever believes it has committed more spend for any wallet    *)
(* than that wallet's known balance." If TLC finds ANY reachable state    *)
(* where this is false, it has found a genuine bug in the protocol       *)
(* logic -- not a hypothetical one, an exact reproducible counterexample. *)
(***************************************************************************)
BalanceInvariant ==
    \A l \in Ledgers, w \in Wallets:
        ledgerCommitted[l][w] <= ledgerKnownBalance[l][w]

=============================================================================
