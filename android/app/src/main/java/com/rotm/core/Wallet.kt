package com.rotm.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import net.i2p.crypto.eddsa.EdDSAEngine
import net.i2p.crypto.eddsa.EdDSAPrivateKey
import net.i2p.crypto.eddsa.EdDSAPublicKey
import net.i2p.crypto.eddsa.spec.EdDSANamedCurveTable
import net.i2p.crypto.eddsa.spec.EdDSAParameterSpec
import net.i2p.crypto.eddsa.spec.EdDSAPrivateKeySpec
import net.i2p.crypto.eddsa.spec.EdDSAPublicKeySpec
import java.io.File
import java.nio.charset.StandardCharsets
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import java.util.Arrays

/**
 * Custom exception for insufficient offline balance.
 * Corresponds to Python `InsufficientOfflineBalance`.
 */
class InsufficientOfflineBalance(message: String) : Exception(message)

/**
 * Custom exception for exceeding offline spending cap.
 * Corresponds to Python `OfflineCapExceeded`.
 */
class OfflineCapExceeded(message: String) : Exception(message)

/**
 * Custom exception for invalid transaction structure or signature.
 * Corresponds to Python `InvalidTransaction`.
 */
class InvalidTransaction(message: String) : Exception(message)

/**
 * Represents the persisted state of a Wallet for serialization.
 */
@Serializable
private data class WalletState(
    val pubkeyHex: String,
    val seedHex: String,
    val balancePaise: Long,
    val nonce: Int,
    val offlineCapPaise: Long,
    val offlineSpentPaise: Long,
    val outbox: List<Transaction>
)

/**
 * An offline-capable wallet identity with local ledger view.
 * Corresponds to the Python `Wallet` class in core/transaction.py.
 */
class Wallet(
    private val offlineCapPaise: Long = 200_000,
    seed: ByteArray? = null
) {

    private val keyFactory: KeyFactory = KeyFactory.getInstance("EdDSA", "BC")
    private val eddsaSpec: EdDSAParameterSpec = EdDSANamedCurveTable.ED_25519
    private val secureRandom = SecureRandom()

    // Ed25519 keypair
    private var privateKey: EdDSAPrivateKey
    private var publicKey: EdDSAPublicKey
    val pubkeyHex: String

    // Wallet state
    var balancePaise: Long = 0
    var nonce: Int = 0
    var offlineSpentPaise: Long = 0
    var outbox: MutableList<Transaction> = mutableListOf()

    init {
        val keyPair = if (seed != null) {
            generateKeyPairFromSeed(seed)
        } else {
            generateRandomKeyPair()
        }
        privateKey = keyPair.first
        publicKey = keyPair.second
        pubkeyHex = publicKey.getEncoded().toHexString()
    }

    /**
     * Generates a random Ed25519 keypair.
     * Corresponds to Python `nacl.signing.SigningKey.generate()`.
     */
    private fun generateRandomKeyPair(): Pair<EdDSAPrivateKey, EdDSAPublicKey> {
        val keyPairGenerator = java.security.KeyPairGenerator.getInstance("EdDSA", "BC")
        keyPairGenerator.initialize(eddsaSpec, secureRandom)
        val keyPair = keyPairGenerator.generateKeyPair()
        return Pair(keyPair.private as EdDSAPrivateKey, keyPair.public as EdDSAPublicKey)
    }

    /**
     * Generates an Ed25519 keypair from a 32-byte seed.
     * Corresponds to Python `nacl.signing.SigningKey(seed)`.
     */
    private fun generateKeyPairFromSeed(seed: ByteArray): Pair<EdDSAPrivateKey, EdDSAPublicKey> {
        require(seed.size == 32) { "Seed must be 32 bytes" }
        val privateKeySpec = EdDSAPrivateKeySpec(seed, eddsaSpec)
        val privateKey = keyFactory.generatePrivate(privateKeySpec) as EdDSAPrivateKey
        val publicKeyBytes = privateKey.getA().toByteArray() // Derive public from private
        val publicKeySpec = EdDSAPublicKeySpec(publicKeyBytes, eddsaSpec)
        val publicKey = keyFactory.generatePublic(publicKeySpec) as EdDSAPublicKey
        return Pair(privateKey, publicKey)
    }

    /**
     * Simulates a sync event that confirms new balance (e.g. after reconnecting).
     * Corresponds to Python `Wallet.fund()`.
     */
    fun fund(amountPaise: Long) {
        if (amountPaise <= 0) throw InvalidTransaction("Fund amount must be positive")
        balancePaise += amountPaise
        offlineSpentPaise = 0 // cap resets on confirmed sync
    }

    /**
     * Creates a new signed transaction.
     * Corresponds to Python `Wallet.create_transaction()`.
     *
     * @throws InsufficientOfflineBalance if amount exceeds known balance
     * @throws OfflineCapExceeded if cumulative offline spend would exceed cap
     * @throws InvalidTransaction if amount is not positive
     */
    fun createTransaction(recipientPub: String, amountPaise: Long): Transaction {
        if (amountPaise <= 0) throw InvalidTransaction("Amount must be positive")

        if (amountPaise > balancePaise) {
            throw InsufficientOfflineBalance(
                "Amount $amountPaise exceeds known balance $balancePaise"
            )
        }

        val projectedSpend = offlineSpentPaise + amountPaise
        if (projectedSpend > offlineCapPaise) {
            throw OfflineCapExceeded(
                "Offline spend $projectedSpend would exceed cap $offlineCapPaise. " +
                "Sync to a server or trusted node to reset the cap."
            )
        }

        val txn = Transaction(
            senderPub = pubkeyHex,
            recipientPub = recipientPub,
            amount = amountPaise,
            nonce = nonce,
            timestamp = System.currentTimeMillis() / 1000, // Unix seconds like Python time.time()
            signature = null,
            txnId = ""
        )

        // Sign the transaction
        val signatureBytes = sign(txn.signingPayload())
        val signatureHex = signatureBytes.toHexString()

        val signedTxn = txn.copy(signature = signatureHex)
        val txnWithId = signedTxn.withComputedId()

        // Optimistically apply locally
        balancePaise -= amountPaise
        offlineSpentPaise += amountPaise
        nonce++
        outbox.add(txnWithId)

        return txnWithId
    }

    /**
     * Signs the given data with the wallet's private key.
     * Corresponds to Python `self.signing_key.sign(payload).signature`.
     */
    private fun sign(data: ByteArray): ByteArray {
        val signature = Signature.getInstance("EdDSA", "BC")
        signature.initSign(privateKey)
        signature.update(data)
        return signature.sign()
    }

    /**
     * Verifies a transaction's signature integrity only.
     * Does NOT check balance/double-spend (that's the ledger's job).
     * Corresponds to Python `Wallet.verify_transaction()`.
     */
    companion object {
        fun verifyTransaction(txn: Transaction): Boolean {
            if (txn.signature == null || txn.signature!.isEmpty()) return false
            try {
                val verifyKey = KeyFactory.getInstance("EdDSA", "BC")
                    .generatePublic(
                        X509EncodedKeySpec(txn.senderPub.hexToByteArray())
                    ) as EdDSAPublicKey

                val signature = Signature.getInstance("EdDSA", "BC")
                signature.initVerify(verifyKey)
                signature.update(txn.signingPayload())
                return signature.verify(txn.signature!.hexToByteArray())
            } catch (e: Exception) {
                return false
            }
        }
    }

    /**
     * Persists wallet state to a local JSON file.
     * Corresponds to Python `Wallet.save_state()`.
     */
    fun saveState(filepath: String) {
        val seedHex = privateKey.getSeed().toHexString()
        val state = WalletState(
            pubkeyHex = pubkeyHex,
            seedHex = seedHex,
            balancePaise = balancePaise,
            nonce = nonce,
            offlineCapPaise = offlineCapPaise,
            offlineSpentPaise = offlineSpentPaise,
            outbox = outbox.toList()
        )
        val json = Json { prettyPrint = true }
        val jsonString = json.encodeToString(state)
        File(filepath).writeText(jsonString, StandardCharsets.UTF_8)
    }

    /**
     * Loads wallet state from a local JSON file.
     * Corresponds to Python `Wallet.load_state()`.
     */
    fun loadState(filepath: String) {
        val file = File(filepath)
        if (!file.exists()) return

        val json = Json { ignoreUnknownKeys = true }
        val jsonString = file.readText(StandardCharsets.UTF_8)
        val state = json.decodeFromString<WalletState>(jsonString)

        // Reconstruct keypair from seed
        val seedBytes = state.seedHex.hexToByteArray()
        val keyPair = generateKeyPairFromSeed(seedBytes)
        privateKey = keyPair.first
        publicKey = keyPair.second
        // pubkeyHex should match, but we trust the seed

        balancePaise = state.balancePaise
        nonce = state.nonce
        offlineSpentPaise = state.offlineSpentPaise
        outbox = state.outbox.toMutableList()
    }

    /**
     * Factory method to load a Wallet instance directly from a saved state file.
     * Corresponds to Python `Wallet.from_state_file()`.
     */
    companion object {
        fun fromStateFile(filepath: String): Wallet {
            val wallet = Wallet()
            wallet.loadState(filepath)
            return wallet
        }
    }
}

/**
 * Extension functions for hex encoding/decoding.
 */
private fun ByteArray.toHexString(): String {
    return joinToString("") { "%02x".format(it) }
}

private fun String.hexToByteArray(): ByteArray {
    require(length % 2 == 0) { "Hex string must have even length" }
    return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}
