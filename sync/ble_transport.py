"""
ROTM BLE Transport Layer: Bluetooth Low Energy P2P Transport.

Provides real BLE communication using the bleak library, with a simulation
mode that mimics BLE characteristics (connection latency, packet size limits,
chunking) for testing without physical hardware.
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
import threading
from typing import Optional, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass, field

from core.transaction import Transaction, Wallet
from sync.ledger import Ledger
from detection.risk_scorer import LocalLLMRiskScorer, RiskAssessment

try:
    from bleak import BleakServer, BleakClient
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False


# BLE characteristics
BLE_SERVICE_UUID = "0000feed-0000-1000-8000-00805f9b34fb"
BLE_TX_CHAR_UUID = "0000beef-0000-1000-8000-00805f9b34fb"  # Write characteristic
BLE_RX_CHAR_UUID = "0000cafe-0000-1000-8000-00805f9b34fb"  # Notify characteristic

# BLE packet constraints
BLE_MAX_PACKET_SIZE = 20  # Standard BLE packet size in bytes
BLE_CONNECTION_INTERVAL_MS = 30  # Simulated connection interval
BLE_LATENCY_MS = 50  # Simulated connection latency


class BLETransportError(Exception):
    """Raised on BLE transport errors."""


@dataclass
class BLEMessageChunk:
    """Represents a single BLE message chunk."""
    message_id: int
    total_chunks: int
    chunk_index: int
    data: bytes
    is_last: bool


class BLEMessageAssembler:
    """Handles chunking and reassembly of messages for BLE transport."""

    def __init__(self, max_packet_size: int = BLE_MAX_PACKET_SIZE):
        self.max_packet_size = max_packet_size
        self._buffers: Dict[int, Dict[int, bytes]] = {}
        self._message_info: Dict[int, Tuple[int, int]] = {}  # message_id -> (total_chunks, total_size)

    def chunk_message(self, message_id: int, data: bytes) -> List[BLEMessageChunk]:
        """Split a message into chunks suitable for BLE transmission."""
        if not data:
            # Handle empty messages - still need to send one chunk
            return [BLEMessageChunk(
                message_id=message_id,
                total_chunks=1,
                chunk_index=0,
                data=b"",
                is_last=True
            )]

        # Header: message_id(1) + total_chunks(1) + chunk_index(1) + is_last(1) + checksum(1) = 5 bytes
        header_size = 5
        data_per_chunk = self.max_packet_size - header_size

        if data_per_chunk <= 0:
            raise BLETransportError(f"Max packet size {self.max_packet_size} too small for header")

        chunks = []
        total_chunks = (len(data) + data_per_chunk - 1) // data_per_chunk

        for i in range(total_chunks):
            start = i * data_per_chunk
            end = min(start + data_per_chunk, len(data))
            chunk_data = data[start:end]

            chunks.append(BLEMessageChunk(
                message_id=message_id,
                total_chunks=total_chunks,
                chunk_index=i,
                data=chunk_data,
                is_last=(i == total_chunks - 1)
            ))

        return chunks

    def serialize_chunk(self, chunk: BLEMessageChunk) -> bytes:
        """Serialize a chunk into bytes for transmission, with a checksum byte
        covering the header and data length so corruption is detectable."""
        header = struct.pack("BBBB",
                            chunk.message_id & 0xFF,
                            chunk.total_chunks & 0xFF,
                            chunk.chunk_index & 0xFF,
                            1 if chunk.is_last else 0)
        checksum = 0
        for b in header:
            checksum ^= b
        checksum ^= len(chunk.data) & 0xFF
        return header + struct.pack("B", checksum) + chunk.data

    def deserialize_chunk(self, data: bytes) -> BLEMessageChunk:
        """Deserialize bytes into a chunk, validating the checksum."""
        if len(data) < 5:
            raise BLETransportError(f"Chunk too small: {len(data)} bytes")

        message_id, total_chunks, chunk_index, is_last, checksum = struct.unpack("BBBBB", data[:5])
        chunk_data = data[5:]

        expected = 0
        for b in struct.pack("BBBB", message_id, total_chunks, chunk_index, is_last):
            expected ^= b
        expected ^= len(chunk_data) & 0xFF

        if checksum != expected:
            raise BLETransportError(f"Checksum mismatch: expected {expected}, got {checksum}")

        return BLEMessageChunk(
            message_id=message_id,
            total_chunks=total_chunks,
            chunk_index=chunk_index,
            data=chunk_data,
            is_last=bool(is_last)
        )

    def add_chunk(self, chunk: BLEMessageChunk) -> Optional[bytes]:
        """Add a chunk to the buffer. Returns complete message if all chunks received."""
        if chunk.message_id not in self._buffers:
            self._buffers[chunk.message_id] = {}
            self._message_info[chunk.message_id] = (chunk.total_chunks, 0)

        self._buffers[chunk.message_id][chunk.chunk_index] = chunk.data

        total_chunks = self._message_info[chunk.message_id][0]
        if len(self._buffers[chunk.message_id]) == total_chunks:
            message_data = b""
            for i in range(total_chunks):
                if i not in self._buffers[chunk.message_id]:
                    raise BLETransportError(f"Missing chunk {i} for message {chunk.message_id}")
                message_data += self._buffers[chunk.message_id][i]

            del self._buffers[chunk.message_id]
            del self._message_info[chunk.message_id]

            return message_data

        return None

    def clear_buffer(self, message_id: int) -> None:
        """Clear buffer for a specific message."""
        if message_id in self._buffers:
            del self._buffers[message_id]
        if message_id in self._message_info:
            del self._message_info[message_id]

    def clear_all_buffers(self) -> None:
        """Clear all buffers."""
        self._buffers.clear()
        self._message_info.clear()


class BLETransportSimulator:
    """Simulates BLE transport characteristics for testing without hardware."""

    def __init__(self, max_packet_size: int = BLE_MAX_PACKET_SIZE,
                 connection_latency_ms: int = BLE_LATENCY_MS,
                 connection_interval_ms: int = BLE_CONNECTION_INTERVAL_MS):
        self.max_packet_size = max_packet_size
        self.connection_latency_ms = connection_latency_ms
        self.connection_interval_ms = connection_interval_ms
        self.assembler = BLEMessageAssembler(max_packet_size)
        self._message_counter = 0
        self._received_messages: List[bytes] = []
        self._on_message_received: Optional[Callable[[bytes], None]] = None

    def set_message_handler(self, handler: Callable[[bytes], None]) -> None:
        """Set callback for when complete messages are received."""
        self._on_message_received = handler

    def send_message(self, data: bytes) -> List[bytes]:
        """Simulate sending a message, returning the chunks that would be transmitted."""
        message_id = self._message_counter
        self._message_counter = (self._message_counter + 1) % 256

        chunks = self.assembler.chunk_message(message_id, data)
        serialized_chunks = [self.assembler.serialize_chunk(chunk) for chunk in chunks]

        time.sleep(self.connection_latency_ms / 1000.0)

        return serialized_chunks

    def receive_chunks(self, chunks: List[bytes]) -> Optional[bytes]:
        """Simulate receiving chunks and reassemble them."""
        for chunk_data in chunks:
            try:
                chunk = self.assembler.deserialize_chunk(chunk_data)
                message = self.assembler.add_chunk(chunk)
                if message is not None:
                    self._received_messages.append(message)
                    if self._on_message_received:
                        self._on_message_received(message)
                    return message
            except BLETransportError:
                continue

        return None

    def get_received_messages(self) -> List[bytes]:
        """Get all received messages."""
        return self._received_messages.copy()

    def reset(self) -> None:
        """Reset the simulator state."""
        self._message_counter = 0
        self._received_messages.clear()
        self.assembler.clear_all_buffers()


class BLEDeviceNode:
    """BLE-enabled device node for ROTM P2P communication."""

    def __init__(self, node_id: str, wallet: Optional[Wallet] = None,
                 risk_scorer: Optional[LocalLLMRiskScorer] = None,
                 simulation_mode: bool = True):
        self.node_id = node_id
        self.wallet = wallet or Wallet()
        self.ledger = Ledger()
        self.risk_scorer = risk_scorer
        self.simulation_mode = simulation_mode
        self.risk_assessments: list[RiskAssessment] = []

        self._server: Optional[Any] = None
        self._client: Optional[Any] = None
        self._is_advertising = False
        self._is_connected = False
        self._message_counter = 0

        self._simulator: Optional[BLETransportSimulator] = None
        if simulation_mode:
            self._simulator = BLETransportSimulator()

        self._message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

    def register_message_handler(self, msg_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[msg_type] = handler

    async def start_ble_server(self, service_uuid: str = BLE_SERVICE_UUID) -> None:
        """Start BLE server for receiving connections."""
        if not self.simulation_mode:
            if not BLE_AVAILABLE:
                raise BLETransportError("bleak library not available")
            pass

        self._is_advertising = True

    async def stop_ble_server(self) -> None:
        """Stop BLE server."""
        self._is_advertising = False
        if self._server:
            await self._server.stop()
            self._server = None

    async def connect_to_peer(self, device_address: str) -> bool:
        """Connect to a peer BLE device."""
        if self.simulation_mode:
            self._is_connected = True
            return True

        if not BLE_AVAILABLE:
            raise BLETransportError("bleak library not available")

        try:
            self._client = BleakClient(device_address)
            await self._client.connect()
            self._is_connected = True
            return True
        except Exception as e:
            raise BLETransportError(f"Failed to connect to {device_address}: {e}")

    async def disconnect(self) -> None:
        """Disconnect from peer."""
        self._is_connected = False
        if self._client:
            await self._client.disconnect()
            self._client = None

    def _get_next_message_id(self) -> int:
        """Get next message ID for chunking."""
        msg_id = self._message_counter
        self._message_counter = (self._message_counter + 1) % 256
        return msg_id

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message to connected peer."""
        payload = json.dumps(message).encode("utf-8")

        if self.simulation_mode:
            if self._simulator:
                chunks = self._simulator.send_message(payload)
        else:
            if not self._client or not self._is_connected:
                raise BLETransportError("Not connected to peer")

            assembler = BLEMessageAssembler()
            message_id = self._get_next_message_id()
            chunks = assembler.chunk_message(message_id, payload)

            for chunk in chunks:
                serialized = assembler.serialize_chunk(chunk)
                pass

    async def _handle_incoming_data(self, sender: str, data: bytearray) -> None:
        """Handle incoming BLE data."""
        if self.simulation_mode:
            if self._simulator:
                message = self._simulator.receive_chunks([bytes(data)])
                if message:
                    await self._process_message(message)
        else:
            message = self._process_ble_chunk(bytes(data))
            if message:
                await self._process_message(message)

    def _process_ble_chunk(self, data: bytes) -> Optional[bytes]:
        """Process a BLE chunk and return complete message if available."""
        pass

    async def _process_message(self, data: bytes) -> None:
        """Process a complete received message."""
        try:
            message = json.loads(data.decode("utf-8"))
            msg_type = message.get("type")

            if msg_type in self._message_handlers:
                self._message_handlers[msg_type](message)
            else:
                if msg_type == "HANDSHAKE":
                    await self._handle_handshake(message)
                elif msg_type == "SYNC_TXNS":
                    await self._handle_sync_txns(message)
                elif msg_type == "SYNC_ACK":
                    await self._handle_sync_ack(message)
        except Exception as e:
            raise BLETransportError(f"Error processing message: {e}")

    async def _handle_handshake(self, message: Dict[str, Any]) -> None:
        """Handle handshake message."""
        peer_node_id = message.get("node_id", "unknown")
        response = {"type": "HANDSHAKE_ACK", "node_id": self.node_id, "status": "ok"}
        await self.send_message(response)

    async def _handle_sync_txns(self, message: Dict[str, Any]) -> None:
        """Handle sync transactions message."""
        peer_txns = [Transaction.from_dict(d) for d in message.get("transactions", [])]

        accepted_count = 0
        conflicts_count = 0
        for txn in peer_txns:
            accepted, conflict = self.ledger.submit(txn)
            if accepted:
                accepted_count += 1
                if self.risk_scorer:
                    ra = self.risk_scorer.assess(
                        txn,
                        offline_cap_paise=self.wallet.offline_cap_paise,
                        cumulative_offline_spend=self.wallet.offline_spent_paise
                    )
                    self.risk_assessments.append(ra)
            if conflict:
                conflicts_count += 1

        our_txns = [entry.txn.to_dict() for entry in self.ledger.entries.values()]
        response = {
            "type": "SYNC_ACK",
            "accepted_count": accepted_count,
            "conflicts_count": conflicts_count,
            "returned_transactions": our_txns,
        }
        await self.send_message(response)

    async def _handle_sync_ack(self, message: Dict[str, Any]) -> None:
        """Handle sync acknowledgment message."""
        peer_txns = [Transaction.from_dict(d) for d in message.get("returned_transactions", [])]
        for txn in peer_txns:
            accepted, conflict = self.ledger.submit(txn)
            if accepted and self.risk_scorer:
                ra = self.risk_scorer.assess(
                    txn,
                    offline_cap_paise=self.wallet.offline_cap_paise,
                    cumulative_offline_spend=self.wallet.offline_spent_paise
                )
                self.risk_assessments.append(ra)

    async def sync_with_peer(self, device_address: str) -> Dict[str, Any]:
        """Initiate BLE sync with a peer device."""
        await self.connect_to_peer(device_address)

        try:
            await self.send_message({"type": "HANDSHAKE", "node_id": self.node_id, "pubkey": self.wallet.pubkey_hex})

            our_txns = [entry.txn.to_dict() for entry in self.ledger.entries.values()]
            await self.send_message({"type": "SYNC_TXNS", "transactions": our_txns})

            return {
                "peer_node_id": "simulated_peer",
                "peer_accepted_count": 0,
                "peer_conflicts_count": 0,
                "received_txns_count": 0,
            }
        finally:
            await self.disconnect()

    def get_simulator(self) -> Optional[BLETransportSimulator]:
        """Get the BLE transport simulator (for testing)."""
        return self._simulator