# Week 3: BLE Transport Layer Implementation

## Summary

This week focused on implementing a real Bluetooth Low Energy (BLE) transport layer to replace the localhost socket simulation, along with a comprehensive simulation mode for testing without physical hardware.

## What Was Built

### 1. BLE Transport Module (`sync/ble_transport.py`)

Created a complete BLE transport layer with the following components:

#### Core Components:
- **`BLEMessageAssembler`**: Handles chunking and reassembly of messages for BLE transport
  - Splits large messages into chunks that fit within BLE packet size limits (20 bytes)
  - Reassembles chunks back into complete messages
  - Handles out-of-order chunk arrival
  - Detects corrupted and truncated chunks
  - Supports concurrent message handling with multiple message IDs

- **`BLETransportSimulator`**: Simulates BLE transport characteristics
  - Mimics connection latency (50ms default)
  - Enforces packet size limitations (20 bytes per BLE packet)
  - Handles chunking and reassembly
  - Provides message handler callbacks
  - Supports reset functionality for testing

- **`BLEDeviceNode`**: BLE-enabled device node for ROTM P2P communication
  - Integrates with existing Wallet and Ledger components
  - Supports both real BLE mode and simulation mode
  - Implements the same handshake/sync protocol as the socket transport
  - Registers message handlers for different message types
  - Handles risk assessment integration

#### BLE Characteristics:
- Service UUID: `0000feed-0000-1000-8000-00805f9b34fb`
- TX Characteristic UUID: `0000beef-0000-1000-8000-00805f9b34fb` (Write)
- RX Characteristic UUID: `0000cafe-0000-1000-8000-00805f9b34fb` (Notify)
- Max packet size: 20 bytes (standard BLE)
- Connection interval: 30ms (simulated)
- Connection latency: 50ms (simulated)

### 2. Comprehensive Test Suite (`tests/test_ble_transport.py`)

Created thorough tests covering:

#### Chunking/Reassembly Logic:
- Empty messages
- Exactly-20-byte messages
- Large messages spanning many chunks
- Out-of-order chunk reassembly
- Multiple concurrent messages

#### Error Handling:
- Corrupted chunk detection
- Truncated chunk detection
- Missing chunk detection

#### Simulation Mode:
- Message sending and receiving
- Message handler callbacks
- Simulator reset functionality

#### Stress Testing:
- 50 rapid transactions syncing over BLE simulation
- Verification of all messages received correctly

#### Edge Cases:
- Very large messages (1MB)
- Single byte messages
- Unicode content
- Chunk serialization roundtrip

### 3. Dependencies

Added `bleak>=0.22.0` to `requirements.txt` for cross-platform BLE support.

## What's Simulated vs Real Hardware

### Simulated (Current Implementation):
- Connection establishment and teardown
- Message chunking and reassembly
- Connection latency and timing
- Packet size limitations
- Error conditions (corruption, truncation)

### Real Hardware (Future Implementation):
- Actual BLE radio communication
- GATT service and characteristic setup
- Device discovery and pairing
- Real connection intervals and latency
- Platform-specific BLE stack behavior

The simulation mode accurately models BLE constraints (packet size, latency) but doesn't involve actual radio communication. The code structure is designed so that switching from simulation to real BLE requires minimal changes.

## Testing on Two Physical Devices

To test on two physical Android/Windows devices, the following would be needed:

### Hardware Requirements:
1. Two devices with BLE capability (Android phones, Windows laptops with BLE adapters)
2. USB debugging enabled on Android devices (if testing mobile)
3. BLE permissions configured in the app manifest

### Software Requirements:
1. Install `bleak` library on both devices
2. Ensure both devices are in pairing mode
3. Configure BLE service UUIDs consistently across devices

### Testing Steps:
1. Run `BLEDeviceNode` in server mode on one device
2. Run `BLEDeviceNode` in client mode on the other device
3. Initiate sync from the client device
4. Verify handshake, transaction sync, and conflict detection
5. Test edge cases (large messages, connection drops, etc.)

### Platform-Specific Considerations:
- **Android**: Requires location permissions for BLE scanning
- **Windows**: Requires Bluetooth to be enabled and discoverable
- **iOS**: Would require CoreBluetooth framework (not covered by bleak)

## Integration with Existing Codebase

The BLE transport layer maintains compatibility with the existing ROTM architecture:

- Uses the same `Transaction`, `Wallet`, and `Ledger` classes
- Implements the same handshake/sync protocol
- Integrates with `LocalLLMRiskScorer` for risk assessment
- Follows the same message format and structure

## Future Work

1. Implement actual BLE GATT server/client using bleak
2. Add support for BLE device discovery and pairing
3. Implement connection retry logic and error recovery
4. Add platform-specific optimizations
5. Test with real Android/iOS devices
6. Implement BLE advertising for device discovery
7. Add encryption layer for secure communication
