# Changelog — Configuration Engine v1.0

All notable changes to the Configuration Engine will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-29

### Added
- **CapabilityModel** — typed capability set with validation (`Capability`, `CapabilityModel`, `validate_capability_model`)
- **CapabilityRegistry** — 9 client profiles (V2RayNG, sing-box, Hiddify, V2RayN, V2RayTun, Streisand, NekoBox, FoXray, Clash)
- **TransportConfig** — 12 typed dataclasses replacing `dict[str, Any]` (XHttpConfig, WebSocketConfig, GrpcConfig, HttpUpgradeConfig, RealityConfig, Hysteria2Config, TuicConfig, TrojanConfig, WireGuardConfig, ShadowsocksConfig, VLessConfig, VMessConfig)
- **TransportSerializer** — 11 serializers with `uri_params()` method for transport-specific query generation
- **TransportRegistry** — registry pattern for transport serializers (11 transports registered)
- **UriExporter** — capability-aware URI generation, replaces legacy `_build_vless_uri()`
- **JsonExporter / YamlExporter** — multi-format export support
- **ExporterRegistry** — format registry (uri, json, yaml)
- **SubscriptionBuilder** — multi-config subscription assembly
- **UriValueSerializer** — type-safe URI value serialization (fixes BUG-001)

### Changed
- **Legacy `_build_vless_uri()`** → **UriExporter + TransportRegistry** (3 call sites updated)
- **String concatenation URI building** → **Type-safe UriExporter + TransportRegistry**
- **Hardcoded transport logic** → **TransportSerializer + TransportRegistry**

### Removed
- String concatenation `params.append()` + `&.join()`
- Manual `fp=chrome` append
- Hardcoded `type=tcp&security=reality...` strings
- Duplicate `_build_vless_uri()` implementations (2 services → 1 implementation)

### Fixed
- **BUG-001** — Android nil pointer crash from invalid JSON (`str(v)` → `json.dumps()`)

### Architecture
- ADR-001 through ADR-006 implemented
- Registry pattern for OCP compliance
- Capability-based routing (O(N+M) vs O(N×M))
- No `dict[str, Any]` in public contracts

### Breaking Changes
- None (internal refactoring, same external API)

### Migration Notes
- Zero-config migration (legacy methods now delegate to new impl)
- Existing clients automatically get capability-aware output
- No changes to subscription URLs or client behavior

### Known Limitations
- Production `inbounds.json` required for live testing
- Hysteria2/TUIC/WireGuard/Shadowsocks transports untested in production
- QR code exporter not yet implemented

---

## [Unreleased]

### Planned
- QR code exporter
- Production validation of Hysteria2/TUIC/WireGuard/Shadowsocks
- Client-specific capability profile auto-detection