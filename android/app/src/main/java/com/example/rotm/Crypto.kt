package com.example.rotm


import org.bouncycastle.crypto.AsymmetricCipherKeyPair
import org.bouncycastle.crypto.generators.Ed25519KeyPairGenerator
import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import org.bouncycastle.crypto.params.Ed25519KeyGenerationParameters
import java.security.SecureRandom

/**
 * Ed25519 crypto core - mirrors the Python ROTM crypto module.
 * Handles key generation, signing, and verification for transactions.
 */
object Crypto {

    data class KeyPair(
        val privateKeyHex: String,
        val publicKeyHex: String
    )

    fun generateKeyPair(): KeyPair {
        val generator = Ed25519KeyPairGenerator()
        generator.init(Ed25519KeyGenerationParameters(SecureRandom()))
        val keyPair: AsymmetricCipherKeyPair = generator.generateKeyPair()

        val privateKey = keyPair.private as Ed25519PrivateKeyParameters
        val publicKey = keyPair.public as Ed25519PublicKeyParameters

        return KeyPair(
            privateKeyHex = privateKey.encoded.toHex(),
            publicKeyHex = publicKey.encoded.toHex()
        )
    }

    fun sign(messageBytes: ByteArray, privateKeyHex: String): String {
        val privateKeyParams = Ed25519PrivateKeyParameters(privateKeyHex.hexToBytes(), 0)
        val signer = Ed25519Signer()
        signer.init(true, privateKeyParams)
        signer.update(messageBytes, 0, messageBytes.size)
        return signer.generateSignature().toHex()
    }

    fun verify(messageBytes: ByteArray, signatureHex: String, publicKeyHex: String): Boolean {
        return try {
            val publicKeyParams = Ed25519PublicKeyParameters(publicKeyHex.hexToBytes(), 0)
            val verifier = Ed25519Signer()
            verifier.init(false, publicKeyParams)
            verifier.update(messageBytes, 0, messageBytes.size)
            verifier.verifySignature(signatureHex.hexToBytes())
        } catch (e: Exception) {
            false
        }
    }
}

// --- Hex helpers ---
fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

fun String.hexToBytes(): ByteArray {
    val len = length
    val data = ByteArray(len / 2)
    var i = 0
    while (i < len) {
        data[i / 2] = ((Character.digit(this[i], 16) shl 4) +
                Character.digit(this[i + 1], 16)).toByte()
        i += 2
    }
    return data
}
