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
    /** Deterministic message bytes used for signing/verifying (excludes signature itself). */
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
 * Tracks seen tx IDs and per-sender nonces to catch replay/double-spend attempts
 * in an offline-first, eventually-synced mesh.
 */
object DoubleSpendGuard {

    // txId -> Transaction, all transactions this device has seen/relayed
    private val seenTransactions = ConcurrentHashMap<String, Transaction>()

    // senderPublicKey -> set of nonces already used by that sender
    private val usedNonces = ConcurrentHashMap<String, MutableSet<String>>()

    sealed class CheckResult {
        object Accepted : CheckResult()
        object DuplicateTxId : CheckResult()
        object NonceReused : CheckResult()
        object InvalidSignature : CheckResult()
    }

    /**
     * Validates and registers a transaction. Returns why it was accepted/rejected.
     * Thread-safe: important since BLE transport may deliver from multiple peers concurrently.
     */
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

        // Accept: record it
        seenTransactions[tx.txId] = tx
        senderNonces.add(tx.nonce)
        return CheckResult.Accepted
    }

    fun getTransaction(txId: String): Transaction? = seenTransactions[txId]

    fun allTransactions(): List<Transaction> = seenTransactions.values.toList()

    /** For syncing with peers / merging mesh state after reconnect. */
    fun mergeKnownTransaction(tx: Transaction): CheckResult = check(tx)

    fun clear() {
        seenTransactions.clear()
        usedNonces.clear()
    }
}

