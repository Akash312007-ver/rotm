package com.example.rotm

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.os.ParcelUuid
import android.util.Log
import java.util.UUID
import java.util.zip.CRC32

/**
 * BLE transport layer - mirrors the Python ROTM BLE-simulated transport,
 * now backed by real Android BLE GATT for peer-to-peer transaction relay.
 *
 * Design: one phone advertises as a GATT peripheral with a custom service;
 * the other scans + connects as a GATT central. Transactions are serialized,
 * chunked (BLE MTU is small), checksummed, and reassembled on the other side.
 */
object BleTransport {

    private const val TAG = "ROTM_BLE"

    val SERVICE_UUID: UUID = UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
    val CHARACTERISTIC_UUID: UUID = UUID.fromString("6e400002-b5a3-f393-e0a9-e50e24dcca9e")

    private const val CHUNK_SIZE = 180 // safe under default BLE MTU (~185 usable bytes)

    // --- Chunk framing: [4-byte chunk index][4-byte total chunks][8-byte CRC32][payload] ---

    fun chunkMessage(data: ByteArray): List<ByteArray> {
        val chunks = data.toList().chunked(CHUNK_SIZE)
        val total = chunks.size
        return chunks.mapIndexed { index, chunkBytes ->
            val payload = chunkBytes.toByteArray()
            val crc = CRC32().apply { update(payload) }.value

            val header = ByteArray(16)
            writeIntToBytes(header, 0, index)
            writeIntToBytes(header, 4, total)
            writeLongToBytes(header, 8, crc)

            header + payload
        }
    }

    /** Reassembles chunks (any order) back into the original byte array, or null if incomplete/corrupt. */
    fun reassemble(chunks: List<ByteArray>): ByteArray? {
        if (chunks.isEmpty()) return null

        val parsed = chunks.map { chunk ->
            val index = readIntFromBytes(chunk, 0)
            val total = readIntFromBytes(chunk, 4)
            val crc = readLongFromBytes(chunk, 8)
            val payload = chunk.copyOfRange(16, chunk.size)

            val actualCrc = CRC32().apply { update(payload) }.value
            if (actualCrc != crc) {
                Log.w(TAG, "Chunk $index failed CRC check, discarding")
                return null
            }
            Triple(index, total, payload)
        }

        val total = parsed.first().second
        if (parsed.size != total) return null // missing chunks

        val ordered = parsed.sortedBy { it.first }
        return ordered.fold(ByteArray(0)) { acc, (_, _, payload) -> acc + payload }
    }

    private fun writeIntToBytes(arr: ByteArray, offset: Int, value: Int) {
        arr[offset] = (value shr 24).toByte()
        arr[offset + 1] = (value shr 16).toByte()
        arr[offset + 2] = (value shr 8).toByte()
        arr[offset + 3] = value.toByte()
    }

    private fun readIntFromBytes(arr: ByteArray, offset: Int): Int {
        return ((arr[offset].toInt() and 0xFF) shl 24) or
                ((arr[offset + 1].toInt() and 0xFF) shl 16) or
                ((arr[offset + 2].toInt() and 0xFF) shl 8) or
                (arr[offset + 3].toInt() and 0xFF)
    }

    private fun writeLongToBytes(arr: ByteArray, offset: Int, value: Long) {
        for (i in 0 until 8) {
            arr[offset + i] = (value shr (56 - i * 8)).toByte()
        }
    }

    private fun readLongFromBytes(arr: ByteArray, offset: Int): Long {
        var result = 0L
        for (i in 0 until 8) {
            result = (result shl 8) or (arr[offset + i].toLong() and 0xFF)
        }
        return result
    }

    // --- Advertising (peripheral role) ---

    @SuppressLint("MissingPermission")
    fun startAdvertising(context: Context, onFailure: (Int) -> Unit = {}) {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val advertiser: BluetoothLeAdvertiser? = bluetoothManager.adapter?.bluetoothLeAdvertiser

        if (advertiser == null) {
            Log.e(TAG, "BLE advertising not supported on this device")
            return
        }

        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .build()

        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(SERVICE_UUID))
            .setIncludeDeviceName(true)
            .build()

        val callback = object : AdvertiseCallback() {
            override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
                Log.i(TAG, "BLE advertising started")
            }

            override fun onStartFailure(errorCode: Int) {
                Log.e(TAG, "BLE advertising failed: $errorCode")
                onFailure(errorCode)
            }
        }

        advertiser.startAdvertising(settings, data, callback)
    }

    // --- Scanning (central role) ---

    @SuppressLint("MissingPermission")
    fun startScanning(context: Context, onDeviceFound: (BluetoothDevice) -> Unit) {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val scanner: BluetoothLeScanner? = bluetoothManager.adapter?.bluetoothLeScanner

        if (scanner == null) {
            Log.e(TAG, "BLE scanning not supported on this device")
            return
        }

        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(SERVICE_UUID))
            .build()

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                Log.i(TAG, "Found ROTM peer: ${result.device.address}")
                onDeviceFound(result.device)
            }

            override fun onScanFailed(errorCode: Int) {
                Log.e(TAG, "BLE scan failed: $errorCode")
            }
        }

        scanner.startScan(listOf(filter), settings, callback)
    }
}
