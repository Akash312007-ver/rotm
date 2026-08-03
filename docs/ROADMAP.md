# ROTM Development Roadmap & Implementation Timeline

This roadmap outlines the remaining work required to transition ROTM from a research prototype to a production-ready offline P2P payment framework and research paper publication.

---

## 1. Real Device-to-Device Transport (Bluetooth LE & Wi-Fi Direct)

* **Objective:** Replace localhost socket simulation with native Android / iOS low-level wireless transport wrappers.
* **Key Tasks:**
  - Build Android `BluetoothLeScanner` / `GATT Server` and `WifiP2pManager` (Wi-Fi Direct) transport drivers in Kotlin.
  - Implement Noise Protocol (`Noise_XX`) key exchange over BLE/Wi-Fi Direct for transport-layer security and mutual identity verification.
  - Add peer discovery, automatic mesh connection handshakes, and background scanning.
* **Estimated Effort:** 4 – 6 Weeks
* **Risk Level:** Medium (Handling cross-platform BLE connection instability and background OS execution limits).

---

## 2. Mobile Application UI & Wallet Client

* **Objective:** Deliver a user-facing Flutter or React Native mobile application for Android and iOS.
* **Key Tasks:**
  - Build wallet onboarding, seed generation, and Ed25519 key storage using Android KeyStore / iOS Keychain.
  - Design QR-code fallback payment flows for instant face-to-face payments when radio discovery is delayed.
  - Render real-time risk score indicators (Green/Yellow/Red advisory badges) based on local LLM output.
  - Integrate on-device GGUF runtime (e.g. `llama.cpp` Android bindings or MLC LLM) to execute Gemma 3 4B locally on mobile NPU/GPU without external servers.
* **Estimated Effort:** 3 – 4 Weeks
* **Risk Level:** Medium (GGUF execution memory overhead on mid-range smartphones).

---

## 3. Empirical Research Paper & Benchmark Writeup

* **Objective:** Author and publish a peer-reviewed research paper on offline P2P payment mesh mechanics and local LLM advisory risk scoring.
* **Key Tasks:**
  - Conduct large-scale discrete-event simulations (`sync/mesh_simulator.py`) across mesh topologies (50 to 500 nodes, 1% to 15% malicious nodes).
  - Benchmark local LLM inference latencies and risk scoring accuracy across quantized models (Gemma 3 4B Q4_K_M vs. Phi-4 mini 3B).
  - Draft paper sections: Introduction, Protocol Specification & Bounded Double-Spend Formalism, On-Device Advisory Risk Model, Mesh Simulation Benchmark Results, and Related Work.
* **Estimated Effort:** 2 – 3 Weeks
* **Risk Level:** Low (Simulation framework is already operational).

---

## Overall Project Schedule

| Phase | Milestone | Estimated Duration | Status |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Core Cryptography, Ledger & Local LLM Scorer | 2 Weeks | ✅ **Completed** |
| **Phase 2** | Socket Transport Simulation & End-to-End Demo | 1 Week | ✅ **Completed** |
| **Phase 3** | Native Mobile Transport (BLE & Wi-Fi Direct) | 5 Weeks | ⏳ Planned |
| **Phase 4** | Mobile UI App & On-Device GGUF Runtime | 4 Weeks | ⏳ Planned |
| **Phase 5** | Empirical Benchmarks & Academic Paper Writeup | 3 Weeks | ⏳ Planned |
