"""
ROTM Web Demo: two simulated phones (Alice, Bob) exchanging offline
transactions, with double-spend detection and risk scoring visualized live.

Run: python demo_web.py
Then open: http://localhost:5000
"""

from __future__ import annotations

import time
from flask import Flask, jsonify, render_template_string

from core.transaction import Wallet, Transaction
from sync.ledger import Ledger
from detection.risk_scorer import LocalLLMRiskScorer

app = Flask(__name__)

# --- Global demo state (single-process demo, not for production) ---
state = {
    "alice": None,
    "bob": None,
    "alice_ledger": None,
    "bob_ledger": None,
    "risk_scorer": None,
    "events": [],
}


def log_event(event_type: str, message: str, details: dict | None = None):
    state["events"].insert(0, {
        "type": event_type,
        "message": message,
        "details": details or {},
        "timestamp": time.time(),
    })
    state["events"] = state["events"][:20]  # keep last 20


def init_demo():
    alice = Wallet(offline_cap_paise=200_000)  # Rs 2000 cap
    bob = Wallet(offline_cap_paise=200_000)
    alice.fund(500_000)  # Rs 5000 starting balance
    bob.fund(500_000)

    alice_ledger = Ledger()
    bob_ledger = Ledger()
    alice_ledger.set_known_balance(alice.pubkey_hex, alice.balance_paise)
    alice_ledger.set_known_balance(bob.pubkey_hex, bob.balance_paise)
    bob_ledger.set_known_balance(alice.pubkey_hex, alice.balance_paise)
    bob_ledger.set_known_balance(bob.pubkey_hex, bob.balance_paise)

    state["alice"] = alice
    state["bob"] = bob
    state["alice_ledger"] = alice_ledger
    state["bob_ledger"] = bob_ledger
    state["risk_scorer"] = LocalLLMRiskScorer()
    state["events"] = []
    log_event("info", "Demo initialized: Alice and Bob each start with Rs 5000, Rs 2000 offline cap")


def wallet_view(w: Wallet) -> dict:
    return {
        "pubkey": w.pubkey_hex[:16] + "...",
        "balance_display": f"Rs {w.balance_paise / 100:.2f}",
        "nonce": w.nonce,
        "offline_cap_paise": w.offline_cap_paise,
        "offline_used_paise": w.offline_spent_paise,
        "offline_used_display": f"Rs {w.offline_spent_paise / 100:.2f}",
        "offline_cap_display": f"Rs {w.offline_cap_paise / 100:.2f}",
        "offline_remaining_display": f"Rs {(w.offline_cap_paise - w.offline_spent_paise) / 100:.2f}",
    }


@app.route("/api/state")
def api_state():
    return jsonify({
        "alice": wallet_view(state["alice"]),
        "bob": wallet_view(state["bob"]),
        "events": state["events"],
    })


@app.route("/api/send_normal")
def api_send_normal():
    try:
        alice = state["alice"]
        bob = state["bob"]
        txn = alice.create_transaction(bob.pubkey_hex, 50_000)  # Rs 500
        accepted, conflict = state["alice_ledger"].submit(txn)
        log_event("success", f"Alice sent Rs 500 to Bob (nonce {txn.nonce})",
                   {"txn_id": txn.txn_id[:12], "accepted": accepted})
        return jsonify({"success": True})
    except Exception as e:
        log_event("error", f"Send failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/double_spend")
def api_double_spend():
    try:
        alice = state["alice"]
        bob = state["bob"]

        # Alice spends to Bob normally, recorded on Alice's ledger.
        txn1 = alice.create_transaction(bob.pubkey_hex, 50_000)
        state["alice_ledger"].submit(txn1)

        # Simulate a malicious client: replay the same balance/nonce to
        # spend to a "Carol" recipient, recorded only on Bob's ledger --
        # each ledger alone looks fine until they sync.
        alice.balance_paise += 50_000
        alice.nonce -= 1
        fake_carol = Wallet().pubkey_hex
        txn2 = alice.create_transaction(fake_carol, 50_000)
        state["bob_ledger"].submit(txn2)

        log_event("warning",
                   "Double-spend attempt created: Alice tried to spend the same Rs 500 twice "
                   "(recorded on separate ledgers - won't be caught until sync)",
                   {"txn1": txn1.txn_id[:12], "txn2": txn2.txn_id[:12]})
        return jsonify({"success": True})
    except Exception as e:
        log_event("error", f"Double-spend simulation failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/sync")
def api_sync():
    try:
        conflicts = state["alice_ledger"].merge(state["bob_ledger"])
        state["bob_ledger"].merge(state["alice_ledger"])

        if conflicts:
            log_event("danger",
                       f"SYNC COMPLETE: {len(conflicts)} double-spend conflict(s) detected and rejected!",
                       {"conflicts": [
                           {"sender": c.sender_pub[:12], "hops_to_detect": c.hops_to_detect}
                           for c in conflicts
                       ]})
        else:
            log_event("success", "Sync complete: no conflicts found, ledgers merged cleanly")
        return jsonify({"success": True, "conflicts_found": len(conflicts)})
    except Exception as e:
        log_event("error", f"Sync failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/risk_assessment")
def api_risk_assessment():
    try:
        alice = state["alice"]
        bob = state["bob"]
        # Build a sample "unusual" transaction to score.
        sample = alice.create_transaction(bob.pubkey_hex, 180_000)  # large, near cap
        assessment = state["risk_scorer"].assess(
            sample,
            offline_cap_paise=alice.offline_cap_paise,
            cumulative_offline_spend=alice.offline_spent_paise,
        )
        log_event("info",
                   f"Risk assessment: score {assessment.risk_score} (LLM used: {assessment.used_llm})",
                   {"reasons": assessment.reasons})
        return jsonify({"success": True, "risk_score": assessment.risk_score})
    except Exception as e:
        log_event("error", f"Risk assessment failed: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>ROTM Live Demo</title>
<style>
  body { font-family: system-ui, sans-serif; background: #0f1115; color: #e6e6e6; margin: 0; padding: 24px; }
  h1 { color: #7dd3fc; }
  .panels { display: flex; gap: 20px; margin-bottom: 24px; }
  .panel { flex: 1; background: #1a1d24; border-radius: 12px; padding: 20px; border: 1px solid #2a2e37; }
  .panel h2 { margin-top: 0; }
  .row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #2a2e37; }
  .bar-bg { background: #2a2e37; border-radius: 6px; height: 12px; margin: 8px 0; overflow: hidden; }
  .bar-fill { background: #4ade80; height: 100%; transition: width 0.3s; }
  .bar-fill.warn { background: #facc15; }
  .bar-fill.danger { background: #f87171; }
  .controls { display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; }
  button { background: #2563eb; color: white; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-size: 14px; }
  button.danger { background: #dc2626; }
  button.warn { background: #ca8a04; }
  button:hover { opacity: 0.9; }
  .events { background: #1a1d24; border-radius: 12px; padding: 20px; border: 1px solid #2a2e37; max-height: 400px; overflow-y: auto; }
  .event { padding: 8px 0; border-bottom: 1px solid #2a2e37; font-size: 14px; }
  .event.success { color: #4ade80; }
  .event.warning { color: #facc15; }
  .event.danger { color: #f87171; }
  .event.error { color: #f87171; }
  .event.info { color: #7dd3fc; }
  .event small { color: #888; display: block; margin-top: 2px; }
</style>
</head>
<body>
<h1>ROTM: Resilient Offline Transaction Mesh - Live Demo</h1>

<div class="panels">
  <div class="panel">
    <h2>Alice's Phone</h2>
    <div class="row"><span>Balance</span><span id="alice-balance">-</span></div>
    <div class="row"><span>Nonce</span><span id="alice-nonce">-</span></div>
    <div>Offline cap usage: <span id="alice-cap-text">-</span></div>
    <div class="bar-bg"><div class="bar-fill" id="alice-bar" style="width:0%"></div></div>
  </div>
  <div class="panel">
    <h2>Bob's Phone</h2>
    <div class="row"><span>Balance</span><span id="bob-balance">-</span></div>
    <div class="row"><span>Nonce</span><span id="bob-nonce">-</span></div>
    <div>Offline cap usage: <span id="bob-cap-text">-</span></div>
    <div class="bar-bg"><div class="bar-fill" id="bob-bar" style="width:0%"></div></div>
  </div>
</div>

<div class="controls">
  <button onclick="call('/api/send_normal')">Send Normal Transaction (Rs 500)</button>
  <button class="danger" onclick="call('/api/double_spend')">Simulate Double-Spend</button>
  <button class="warn" onclick="call('/api/sync')">Trigger Sync</button>
  <button onclick="call('/api/risk_assessment')">Run Risk Assessment</button>
</div>

<div class="events">
  <h2>Event Log</h2>
  <div id="events-list"></div>
</div>

<script>
function call(url) {
  fetch(url).then(r => r.json()).then(() => refresh());
}
function refresh() {
  fetch('/api/state').then(r => r.json()).then(data => {
    document.getElementById('alice-balance').textContent = data.alice.balance_display;
    document.getElementById('alice-nonce').textContent = data.alice.nonce;
    document.getElementById('bob-balance').textContent = data.bob.balance_display;
    document.getElementById('bob-nonce').textContent = data.bob.nonce;

    const alicePct = (data.alice.offline_used_paise / data.alice.offline_cap_paise) * 100;
    const bobPct = (data.bob.offline_used_paise / data.bob.offline_cap_paise) * 100;
    document.getElementById('alice-cap-text').textContent = data.alice.offline_used_display + ' / ' + data.alice.offline_cap_display;
    document.getElementById('bob-cap-text').textContent = data.bob.offline_used_display + ' / ' + data.bob.offline_cap_display;

    const aliceBar = document.getElementById('alice-bar');
    aliceBar.style.width = alicePct + '%';
    aliceBar.className = 'bar-fill' + (alicePct > 80 ? ' danger' : alicePct > 50 ? ' warn' : '');

    const bobBar = document.getElementById('bob-bar');
    bobBar.style.width = bobPct + '%';
    bobBar.className = 'bar-fill' + (bobPct > 80 ? ' danger' : bobPct > 50 ? ' warn' : '');

    const list = document.getElementById('events-list');
    list.innerHTML = data.events.map(e =>
      `<div class="event ${e.type}">${e.message}<small>${new Date(e.timestamp*1000).toLocaleTimeString()}</small></div>`
    ).join('') || '<div>No events yet</div>';
  });
}
init = fetch('/api/state').then(r => r.ok ? null : refresh());
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    init_demo()
    app.run(host="0.0.0.0", port=5000, debug=False)
