package com.rotm.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/**
 * Represents an immutable, signed P2P transaction.
 * Corresponds to the Python `Transaction` dataclass in core/transaction.py.
 */
@Serializable
data class Transaction(
    val senderPub: String,
    val recipientPub: String,
    val amount: Long, // paise
    val nonce: Int,
    val timestamp: Long,
    val signature: String? = null,
    val txnId: String = ""
) {

    companion object {
        private const val DOMAIN_SEPARATOR = "ROTM-TXN-v1:"
        private val json = Json { ignoreUnknownKeys = true }
    }

    /**
     * Produces the canonical bytes that get signed (excludes signature and txnId).
     * Corresponds to Python `Transaction.signing_payload()`.
     */
    fun signingPayload(): ByteArray {
        // Create a temporary object with only the fields that are signed
        val payload = TransactionPayload(
            senderPub = senderPub,
            recipientPub = recipientPub,
            amount = amount,
            nonce = nonce,
            timestamp = timestamp
        )
        val jsonString = json.encodeToString(payload)
        return (DOMAIN_SEPARATOR + jsonString).toByteArray(StandardCharsets.UTF_8)
    }

    /**
     * Computes the deterministic transaction ID from the signed payload + signature.
     * Corresponds to Python `Transaction.compute_id()`.
     */
    fun computeId(): String {
        val payloadBytes = signingPayload()
        val signatureBytes = (signature ?: "").toByteArray(StandardCharsets.UTF_8)
        val combined = payloadBytes + signatureBytes
        val digest = MessageDigest.getInstance("SHA-256").digest(combined)
        return digest.joinToString("") { "%02x".format(it) }
    }

    /**
     * Creates a new Transaction with the computed txnId.
     * Corresponds to the Python pattern of setting txn_id after creation.
     */
    fun withComputedId(): Transaction {
        return copy(txnId = computeId())
    }

    /**
     * Serializes the full transaction (including signature and txnId) to JSON string.
     */
    fun toJson(): String = json.encodeToString(this)

    /**
     * Deserializes a Transaction from a JSON string.
     * Corresponds to Python `Transaction.from_dict()`.
     */
    companion object {
        fun fromJson(jsonString: String): Transaction = json.decodeFromString(jsonString)
    }
}

/**
 * Internal payload for signing (excludes signature and txnId).
 * Used to generate the canonical JSON for signing.
 */
@Serializable
private data class TransactionPayload(
    val senderPub: String,
    val recipientPub: String,
    val amount: Long,
    val nonce: Int,
    val timestamp: Long
)
