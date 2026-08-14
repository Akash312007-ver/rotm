package com.example.rotm

import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap

/**
 * Transaction structure - mirrors the Python ROTM transaction model.
 */
data class Transaction(
    val txId: String,
    val senderPublicKey: String,
    val receiverPublicKey: String,
    val amount: Double,
    val timestamp: Long,
    val nonce: String,
    var signature: String = ""
) {
    fun signingPayload(): ByteArray {
        val raw = "$txId|$senderPublicKey|$receiverPublicKey|$amount|$timestamp|$nonce"
        return raw.toByteArray(Charsets.UTF_8)
    }

    fun sign(privateKeyHex: String) {
        signature = Crypto.sign(signingPayload(), privateKeyHex)
    }

    fun isSignatureValid(): Boolean {
        if (signature.isEmpty()) return false
        return Crypto.verify(signingPayload(), signature, senderPublicKey)
    }

    companion object {
        fun computeTxId(senderPublicKey: String, receiverPublicKey: String, amount: Double, timestamp: Long, nonce: String): String {
            val raw = "$senderPublicKey|$receiverPublicKey|$amount|$timestamp|$nonce"
            val digest = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
            return digest.toHex()
        }
    }
}

/**
 * Double-spend detection - mirrors the Python ROTM double-spend module.
 * Persists seen tx IDs/nonces to disk so restarting the app doesn't reset memory.
 */
object DoubleSpendGuard {

    private val seenTransactions = ConcurrentHashMap<String, Transaction>()
    private val usedNonces = ConcurrentHashMap<String, MutableSet<String>>()
    private var prefs: android.content.SharedPreferences? = null

    sealed class CheckResult {
        object Accepted : CheckResult()
        object DuplicateTxId : CheckResult()
        object NonceReused : CheckResult()
        object InvalidSignature : CheckResult()
    }

    fun init(context: android.content.Context) {
        prefs = context.getSharedPreferences("rotm_doublespend_ledger", android.content.Context.MODE_PRIVATE)
        val savedIds = prefs?.getStringSet("seen_tx_ids", emptySet()) ?: emptySet()
        for (id in savedIds) {
            val sender = prefs?.getString("sender_for_$id", null) ?: continue
            val nonce = prefs?.getString("nonce_for_$id", null) ?: continue
            usedNonces.getOrPut(sender) { mutableSetOf() }.add(nonce)
            seenTransactions[id] = Transaction(id, sender, "", 0.0, 0L, nonce)
        }
    }

    @Synchronized
    fun check(tx: Transaction): CheckResult {
        if (!tx.isSignatureValid()) {
            return CheckResult.InvalidSignature
        }
        if (seenTransactions.containsKey(tx.txId)) {
            return CheckResult.DuplicateTxId
        }
        val senderNonces = usedNonces.getOrPut(tx.senderPublicKey) { mutableSetOf() }
        if (senderNonces.contains(tx.nonce)) {
            return CheckResult.NonceReused
        }

        seenTransactions[tx.txId] = tx
        senderNonces.add(tx.nonce)
        persist(tx)
        return CheckResult.Accepted
    }

    private fun persist(tx: Transaction) {
        val p = prefs ?: return
        val current = p.getStringSet("seen_tx_ids", emptySet())?.toMutableSet() ?: mutableSetOf()
        current.add(tx.txId)
        p.edit()
            .putStringSet("seen_tx_ids", current)
            .putString("sender_for_${tx.txId}", tx.senderPublicKey)
            .putString("nonce_for_${tx.txId}", tx.nonce)
            .apply()
    }

    fun getTransaction(txId: String): Transaction? = seenTransactions[txId]
    fun allTransactions(): List<Transaction> = seenTransactions.values.toList()
    fun mergeKnownTransaction(tx: Transaction): CheckResult = check(tx)

    fun clear() {
        seenTransactions.clear()
        usedNonces.clear()
        prefs?.edit()?.clear()?.apply()
    }
}