"""
Tests for BLE transport layer including chunking/reassembly logic and
simulation mode.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import json
import time
import threading
from sync.ble_transport import (
    BLEMessageAssembler, BLETransportSimulator, BLEDeviceNode,
    BLEMessageChunk, BLETransportError, BLE_MAX_PACKET_SIZE
)


class TestBLEMessageAssembler(unittest.TestCase):
    """Tests for the BLE message chunking and reassembly logic."""

    def setUp(self):
        self.assembler = BLEMessageAssembler()

    def test_empty_message(self):
        """Test chunking of an empty message."""
        chunks = self.assembler.chunk_message(1, b"")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].message_id, 1)
        self.assertEqual(chunks[0].total_chunks, 1)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertTrue(chunks[0].is_last)
        self.assertEqual(chunks[0].data, b"")

    def test_exactly_20_byte_message(self):
        """Test chunking of a message that exactly fits in one BLE packet."""
        # 20 bytes total, 5 bytes header (incl. checksum), so 15 bytes of data
        data = b"x" * 15
        chunks = self.assembler.chunk_message(1, data)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].data, data)

    def test_large_message_multiple_chunks(self):
        """Test chunking of a large message spanning many chunks."""
        # 100 bytes of data, 15 bytes per chunk = 7 chunks
        data = b"x" * 100
        chunks = self.assembler.chunk_message(1, data)
        self.assertEqual(len(chunks), 7)

        for i, chunk in enumerate(chunks):
            self.assertEqual(chunk.message_id, 1)
            self.assertEqual(chunk.total_chunks, 7)
            self.assertEqual(chunk.chunk_index, i)
            self.assertEqual(chunk.is_last, (i == 6))

    def test_message_reassembly(self):
        """Test that chunked messages can be reassembled correctly."""
        original_data = b"Hello, BLE World! This is a test message."
        chunks = self.assembler.chunk_message(1, original_data)

        reassembled = None
        for chunk in chunks:
            result = self.assembler.add_chunk(chunk)
            if result is not None:
                reassembled = result

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled, original_data)

    def test_message_reassembly_out_of_order(self):
        """Test reassembly with chunks arriving out of order."""
        original_data = b"Out of order test message with enough data to span multiple chunks."
        chunks = self.assembler.chunk_message(1, original_data)

        chunks.reverse()

        reassembled = None
        for chunk in chunks:
            result = self.assembler.add_chunk(chunk)
            if result is not None:
                reassembled = result

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled, original_data)

    def test_corrupted_chunk_detection(self):
        """Test detection of corrupted chunks."""
        chunks = self.assembler.chunk_message(1, b"Test data")
        serialized = self.assembler.serialize_chunk(chunks[0])

        corrupted = bytearray(serialized)
        corrupted[0] = 0xFF  # Corrupt message_id

        with self.assertRaises(BLETransportError):
            self.assembler.deserialize_chunk(bytes(corrupted))

    def test_truncated_chunk_detection(self):
        """Test detection of truncated chunks."""
        chunks = self.assembler.chunk_message(1, b"Test data")
        serialized = self.assembler.serialize_chunk(chunks[0])

        truncated = serialized[:2]

        with self.assertRaises(BLETransportError):
            self.assembler.deserialize_chunk(truncated)

    def test_missing_chunk_detection(self):
        """Test detection of missing chunks during reassembly."""
        original_data = b"Data that will be split into multiple chunks for testing."
        chunks = self.assembler.chunk_message(1, original_data)

        result = self.assembler.add_chunk(chunks[0])
        self.assertIsNone(result)

    def test_multiple_concurrent_messages(self):
        """Test handling multiple messages concurrently."""
        data1 = b"First message"
        data2 = b"Second message"

        chunks1 = self.assembler.chunk_message(1, data1)
        chunks2 = self.assembler.chunk_message(2, data2)

        all_chunks = [chunks1[0], chunks2[0]]

        results = []
        for chunk in all_chunks:
            result = self.assembler.add_chunk(chunk)
            if result is not None:
                results.append(result)

        self.assertEqual(len(results), 2)
        self.assertIn(data1, results)
        self.assertIn(data2, results)

    def test_clear_buffer(self):
        """Test clearing buffers."""
        chunks = self.assembler.chunk_message(1, b"Test data")
        self.assembler.add_chunk(chunks[0])

        self.assembler.clear_buffer(1)

        self.assertEqual(len(self.assembler._buffers), 0)

    def test_clear_all_buffers(self):
        """Test clearing all buffers."""
        chunks1 = self.assembler.chunk_message(1, b"Test data 1")
        chunks2 = self.assembler.chunk_message(2, b"Test data 2")

        self.assembler.add_chunk(chunks1[0])
        self.assembler.add_chunk(chunks2[0])

        self.assembler.clear_all_buffers()

        self.assertEqual(len(self.assembler._buffers), 0)
        self.assertEqual(len(self.assembler._message_info), 0)


class TestBLETransportSimulator(unittest.TestCase):
    """Tests for the BLE transport simulator."""

    def setUp(self):
        self.simulator = BLETransportSimulator()

    def test_send_and_receive_message(self):
        """Test sending and receiving a message through the simulator."""
        message = {"type": "HANDSHAKE", "node_id": "test_node"}
        data = json.dumps(message).encode("utf-8")

        chunks = self.simulator.send_message(data)
        self.assertGreater(len(chunks), 0)

        received = self.simulator.receive_chunks(chunks)
        self.assertIsNotNone(received)
        self.assertEqual(received, data)

    def test_empty_message_through_simulator(self):
        """Test sending an empty message through the simulator."""
        data = b""
        chunks = self.simulator.send_message(data)
        self.assertEqual(len(chunks), 1)

        received = self.simulator.receive_chunks(chunks)
        self.assertIsNotNone(received)
        self.assertEqual(received, data)

    def test_large_message_through_simulator(self):
        """Test sending a large message through the simulator."""
        large_data = b"x" * 1000
        chunks = self.simulator.send_message(large_data)
        self.assertGreater(len(chunks), 1)

        received = self.simulator.receive_chunks(chunks)
        self.assertIsNotNone(received)
        self.assertEqual(received, large_data)

    def test_message_handler_callback(self):
        """Test that message handler callback is called."""
        received_messages = []

        def handler(data: bytes):
            received_messages.append(data)

        self.simulator.set_message_handler(handler)

        message = {"type": "TEST", "data": "value"}
        data = json.dumps(message).encode("utf-8")

        chunks = self.simulator.send_message(data)
        self.simulator.receive_chunks(chunks)

        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0], data)

    def test_reset(self):
        """Test resetting the simulator."""
        data = json.dumps({"type": "TEST"}).encode("utf-8")
        self.simulator.send_message(data)

        self.simulator.reset()

        self.assertEqual(self.simulator._message_counter, 0)
        self.assertEqual(len(self.simulator._received_messages), 0)
        self.assertEqual(len(self.simulator.assembler._buffers), 0)


class TestBLEDeviceNode(unittest.TestCase):
    """Tests for the BLE device node."""

    def test_device_node_creation(self):
        """Test creating a BLE device node."""
        node = BLEDeviceNode("test_node", simulation_mode=True)
        self.assertEqual(node.node_id, "test_node")
        self.assertTrue(node.simulation_mode)
        self.assertIsNotNone(node.wallet)
        self.assertIsNotNone(node.ledger)
        self.assertIsNotNone(node._simulator)

    def test_message_handler_registration(self):
        """Test registering message handlers."""
        node = BLEDeviceNode("test_node", simulation_mode=True)

        def handler(message: dict):
            pass

        node.register_message_handler("TEST", handler)
        self.assertIn("TEST", node._message_handlers)

    def test_simulator_access(self):
        """Test accessing the simulator."""
        node = BLEDeviceNode("test_node", simulation_mode=True)
        simulator = node.get_simulator()
        self.assertIsNotNone(simulator)
        self.assertIsInstance(simulator, BLETransportSimulator)


class TestBLEStressTest(unittest.TestCase):
    """Stress test for BLE transport with 50 rapid transactions."""

    def test_50_rapid_transactions(self):
        """Simulate 50 rapid transactions syncing over BLE simulation."""
        simulator = BLETransportSimulator()

        transactions = []
        for i in range(50):
            txn_data = {
                "type": "SYNC_TXNS",
                "transactions": [
                    {
                        "sender_pub": f"sender_{i}",
                        "recipient_pub": f"recipient_{i}",
                        "amount_paise": 1000 + i,
                        "nonce": i,
                        "signature": f"sig_{i}"
                    }
                ]
            }
            transactions.append(json.dumps(txn_data).encode("utf-8"))

        all_chunks = []
        for txn in transactions:
            chunks = simulator.send_message(txn)
            all_chunks.extend(chunks)

        received_count = 0
        for chunk in all_chunks:
            result = simulator.receive_chunks([chunk])
            if result is not None:
                received_count += 1

        self.assertEqual(received_count, 50)

        received_messages = simulator.get_received_messages()
        self.assertEqual(len(received_messages), 50)

        for i, msg in enumerate(received_messages):
            original = transactions[i]
            self.assertEqual(msg, original)


class TestBLEEdgeCases(unittest.TestCase):
    """Additional edge case tests for BLE transport."""

    def test_very_large_message(self):
        """Test with a very large message (1MB)."""
        assembler = BLEMessageAssembler()
        large_data = b"x" * (1024 * 1024)

        chunks = assembler.chunk_message(1, large_data)
        self.assertGreater(len(chunks), 1000)

        reassembled = None
        for chunk in chunks:
            result = assembler.add_chunk(chunk)
            if result is not None:
                reassembled = result

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled, large_data)

    def test_single_byte_message(self):
        """Test with a single byte message."""
        assembler = BLEMessageAssembler()
        data = b"A"

        chunks = assembler.chunk_message(1, data)
        self.assertEqual(len(chunks), 1)

        reassembled = None
        for chunk in chunks:
            result = assembler.add_chunk(chunk)
            if result is not None:
                reassembled = result

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled, data)

    def test_unicode_message(self):
        """Test with unicode content."""
        assembler = BLEMessageAssembler()
        data = "Hello, world! test".encode("utf-8")

        chunks = assembler.chunk_message(1, data)

        reassembled = None
        for chunk in chunks:
            result = assembler.add_chunk(chunk)
            if result is not None:
                reassembled = result

        self.assertIsNotNone(reassembled)
        self.assertEqual(reassembled, data)

    def test_chunk_serialization_roundtrip(self):
        """Test that chunk serialization/deserialization is lossless."""
        assembler = BLEMessageAssembler()
        original_data = b"Test data for serialization roundtrip"

        chunks = assembler.chunk_message(1, original_data)

        for chunk in chunks:
            serialized = assembler.serialize_chunk(chunk)
            deserialized = assembler.deserialize_chunk(serialized)

            self.assertEqual(deserialized.message_id, chunk.message_id)
            self.assertEqual(deserialized.total_chunks, chunk.total_chunks)
            self.assertEqual(deserialized.chunk_index, chunk.chunk_index)
            self.assertEqual(deserialized.is_last, chunk.is_last)
            self.assertEqual(deserialized.data, chunk.data)


if __name__ == "__main__":
    unittest.main()
