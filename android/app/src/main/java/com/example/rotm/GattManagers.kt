package com.example.rotm

import android.annotation.SuppressLint
import android.bluetooth.*
import android.content.Context
import android.util.Log

/**
 * GATT server - runs on the RECEIVING phone. Advertises (via BleTransport.startAdvertising)
 * and accepts incoming chunk writes from a connected peer, forwarding them to MeshManager.
 */
class GattServerManager(
    private val context: Context,
    private val mesh: MeshManager
) {
    private val TAG = "ROTM_GATT_SRV"
    private var gattServer: BluetoothGattServer? = null

    @SuppressLint("MissingPermission")
    fun start() {
        val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager

        val callback = object : BluetoothGattServerCallback() {
            override fun onConnectionStateChange(device: BluetoothDevice, status: Int, newState: Int) {
                Log.i(TAG, "Peer ${device.address} connection state: $newState")
            }

            override fun onCharacteristicWriteRequest(
                device: BluetoothDevice,
                requestId: Int,
                characteristic: BluetoothGattCharacteristic,
                preparedWrite: Boolean,
                responseNeeded: Boolean,
                offset: Int,
                value: ByteArray
            ) {
                if (characteristic.uuid == BleTransport.CHARACTERISTIC_UUID) {
                    val sessionKey = device.address
                    mesh.onChunkReceived(sessionKey, value)
                }

                if (responseNeeded) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
                }
            }
        }

        gattServer = bluetoothManager.openGattServer(context, callback)

        val service = BluetoothGattService(BleTransport.SERVICE_UUID, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val characteristic = BluetoothGattCharacteristic(
            BleTransport.CHARACTERISTIC_UUID,
            BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
            BluetoothGattCharacteristic.PERMISSION_WRITE
        )
        service.addCharacteristic(characteristic)
        gattServer?.addService(service)

        Log.i(TAG, "GATT server started, service registered")
    }

    @SuppressLint("MissingPermission")
    fun stop() {
        gattServer?.close()
        gattServer = null
    }
}

/**
 * GATT client - runs on the SENDING phone. Connects to a discovered peer device
 * and writes chunked transaction bytes to their characteristic.
 */
class GattClientManager(private val context: Context) {
    private val TAG = "ROTM_GATT_CLI"
    private var bluetoothGatt: BluetoothGatt? = null
    private var pendingChunks: List<ByteArray> = emptyList()
    private var chunkIndex = 0
    private var onComplete: (() -> Unit)? = null

    @SuppressLint("MissingPermission")
    fun sendTransaction(device: BluetoothDevice, txBytes: ByteArray, onComplete: () -> Unit) {
        this.pendingChunks = BleTransport.chunkMessage(txBytes)
        this.chunkIndex = 0
        this.onComplete = onComplete

        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothGatt.STATE_CONNECTED) {
                    Log.i(TAG, "Connected, discovering services")
                    gatt.discoverServices()
                } else if (newState == BluetoothGatt.STATE_DISCONNECTED) {
                    Log.i(TAG, "Disconnected")
                    gatt.close()
                }
            }

            override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
                val service = gatt.getService(BleTransport.SERVICE_UUID)
                val characteristic = service?.getCharacteristic(BleTransport.CHARACTERISTIC_UUID)
                if (characteristic == null) {
                    Log.e(TAG, "ROTM characteristic not found on peer")
                    return
                }
                writeNextChunk(gatt, characteristic)
            }

            override fun onCharacteristicWrite(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int
            ) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    Log.e(TAG, "Chunk write failed at index $chunkIndex")
                    return
                }
                chunkIndex++
                if (chunkIndex < pendingChunks.size) {
                    writeNextChunk(gatt, characteristic)
                } else {
                    Log.i(TAG, "All chunks sent")
                    this@GattClientManager.onComplete?.invoke()
                    gatt.disconnect()
                }
            }
        }

        bluetoothGatt = device.connectGatt(context, false, callback)
    }

    @SuppressLint("MissingPermission")
    private fun writeNextChunk(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        val chunk = pendingChunks[chunkIndex]
        characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        characteristic.value = chunk
        gatt.writeCharacteristic(characteristic)
    }

    @SuppressLint("MissingPermission")
    fun close() {
        bluetoothGatt?.close()
        bluetoothGatt = null
    }
}
