package com.example.rotm

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.MessageDigest

/**
 * Secure on-device storage for wallet keys and PIN.
 * Uses Android Keystore-backed encryption so keys aren't stored in plain text.
 */
object WalletStore {

    private const val PREFS_NAME = "rotm_secure_wallet"
    private const val KEY_PRIVATE = "private_key_hex"
    private const val KEY_PUBLIC = "public_key_hex"
    private const val KEY_PIN_HASH = "pin_hash"

    private fun prefs(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        return EncryptedSharedPreferences.create(
            context,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    fun hasWallet(context: Context): Boolean {
        val p = prefs(context)
        return p.contains(KEY_PRIVATE) && p.contains(KEY_PUBLIC)
    }

    fun saveWallet(context: Context, privateKeyHex: String, publicKeyHex: String) {
        prefs(context).edit()
            .putString(KEY_PRIVATE, privateKeyHex)
            .putString(KEY_PUBLIC, publicKeyHex)
            .apply()
    }

    fun loadWallet(context: Context): Crypto.KeyPair? {
        val p = prefs(context)
        val priv = p.getString(KEY_PRIVATE, null) ?: return null
        val pub = p.getString(KEY_PUBLIC, null) ?: return null
        return Crypto.KeyPair(priv, pub)
    }

    fun hasPin(context: Context): Boolean = prefs(context).contains(KEY_PIN_HASH)

    fun setPin(context: Context, pin: String) {
        prefs(context).edit().putString(KEY_PIN_HASH, hashPin(pin)).apply()
    }

    fun verifyPin(context: Context, pin: String): Boolean {
        val stored = prefs(context).getString(KEY_PIN_HASH, null) ?: return false
        return stored == hashPin(pin)
    }

    private fun hashPin(pin: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(pin.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
