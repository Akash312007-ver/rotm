package com.example.rotm

import android.bluetooth.BluetoothDevice
import android.content.Context
import android.util.Log
import java.util.UUID

class MeshManager(private val context: Context) {

    private val TAG = "ROTM_MESH"

    var myKeyPair: Crypto.KeyPair? = null
        private set

    private val incomingChunkBuffer = mutableMapOf<String, MutableList<ByteArray>>()

    private val gattServer = GattServerManager(context, this)
    private val gattClient = GattClientManager(context)

    /** Loads existing wallet from secure storage, or creates + saves a new one if none exists. */
    fun initWallet(): Crypto.KeyPair {
        val existing = WalletStore.loadWallet(context)
        if (existing != null) {
            myKeyPair = existing
            return existing
        }
        val kp = Crypto.generateKeyPair()
        WalletStore.saveWallet(context, kp.privateKeyHex, kp.publicKeyHex)
        myKeyPair = kp
        return kp
    }

    fun loadWallet(privateKeyHex: String, publicKeyHex: String) {
        myKeyPair = Crypto.KeyPair(privateKeyHex, publicKeyHex)
    }

    fun createPayment(receiverPublicKey: String, amount: Double): Transaction? {
        val kp = myKeyPair ?: run {
            Log.e(TAG, "No wallet loaded")
            return null
        }

        val timestamp = System.currentTimeMillis()
        val nonce = UUID.randomUUID().toString()
        val txId = Transaction.computeTxId(kp.publicKeyHex, receiverPublicKey, amount, timestamp, nonce)

        val tx = Transaction(
            txId = txId,
            senderPublicKey = kp.publicKeyHex,
            receiverPublicKey = receiverPublicKey,
            amount = amount,
            timestamp = timestamp,
            nonce = nonce
        )
        tx.sign(kp.privateKeyHex)

        val result = DoubleSpendGuard.check(tx)
        if (result != DoubleSpendGuard.CheckResult.Accepted) {
            Log.e(TAG, "Locally created tx rejected: $result")
            return null
        }
        return tx
    }

    fun sendPayment(receiverPublicKey: String, amount: Double, onResult: (Boolean) -> Unit) {
        val tx = createPayment(receiverPublicKey, amount)
        if (tx == null) {
            onResult(false)
            return
        }

        BleTransport.startScanning(context) { device: BluetoothDevice ->
            val txBytes = serializeTx(tx)
            gattClient.sendTransaction(device, txBytes) {
                Log.i(TAG, "Payment ${tx.txId} sent over BLE")
                onResult(true)
            }
        }
    }

    fun serializeTx(tx: Transaction): ByteArray {
        val raw = "${tx.txId}|${tx.senderPublicKey}|${tx.receiverPublicKey}|${tx.amount}|${tx.timestamp}|${tx.nonce}|${tx.signature}"
        return raw.toByteArray(Charsets.UTF_8)
    }

    fun deserializeTx(bytes: ByteArray): Transaction? {
        return try {
            val parts = String(bytes, Charsets.UTF_8).split("|")
            Transaction(
                txId = parts[0],
                senderPublicKey = parts[1],
                receiverPublicKey = parts[2],
                amount = parts[3].toDouble(),
                timestamp = parts[4].toLong(),
                nonce = parts[5],
                signature = parts[6]
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to deserialize tx: ${e.message}")
            null
        }
    }

    fun startReceiving() {
        gattServer.start()
        BleTransport.startAdvertising(context) { errorCode ->
            Log.e(TAG, "Advertising failed: $errorCode")
        }
    }

    fun startDiscovering(onPeerFound: (BluetoothDevice) -> Unit) {
        BleTransport.startScanning(context, onPeerFound)
    }

    fun onChunkReceived(sessionKey: String, chunk: ByteArray) {
        val buffer = incomingChunkBuffer.getOrPut(sessionKey) { mutableListOf() }
        buffer.add(chunk)

        val reassembled = BleTransport.reassemble(buffer) ?: return
        incomingChunkBuffer.remove(sessionKey)

        val tx = deserializeTx(reassembled) ?: return
        val result = DoubleSpendGuard.check(tx)
        Log.i(TAG, "Received tx ${tx.txId}: $result")
    }

    fun balanceOf(publicKeyHex: String): Double {
        val all = DoubleSpendGuard.allTransactions()
        val received = all.filter { it.receiverPublicKey == publicKeyHex }.sumOf { it.amount }
        val sent = all.filter { it.senderPublicKey == publicKeyHex }.sumOf { it.amount }
        return received - sent
    }

    fun transactionHistory(publicKeyHex: String): List<Transaction> {
        return DoubleSpendGuard.allTransactions().filter {
            it.senderPublicKey == publicKeyHex || it.receiverPublicKey == publicKeyHex
        }.sortedByDescending { it.timestamp }
    }
}
