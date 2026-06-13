# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.36.0] - 2026-06-14

Full integration overhaul: modular architecture, strict typing, modern config
flow, and an exhaustive test suite (coverage 99%, mypy --strict clean, hassfest
clean). Existing entities are migrated automatically; no user action required.

### Added
- **Discovery**: a reachable Envoy is now auto-discovered via zeroconf
  (`_enphase-envoy._tcp.local.`) and DHCP; confirm with your Enlighten
  credentials to set it up. The stored host is refreshed automatically if the
  Envoy's IP changes.
- **System Health** panel entry reporting Enphase Enlighten cloud reachability.
- **Repair issue** when local-only mode hides the control entities (firmware 8.x),
  guiding you to enable cloud control; cleared automatically once enabled.
- **Stale device removal**: an individual battery no longer reported by the
  system can be removed from the device page (active batteries and the hub are
  protected).

### Changed
- **Entity unique IDs are now scoped to the config entry** (`{entry_id}_…`)
  instead of a shared `enphase_battery_…` prefix, so two Enphase systems can
  coexist. `ConfigEntry` version bumped to 3 with an automatic migration that
  renames existing entities in place (history and automations are preserved).
- Setup now uses `async_config_entry_first_refresh`: connection failures retry
  (`ConfigEntryNotReady`) and authentication failures trigger reauth
  (`ConfigEntryAuthFailed`), replacing the deferred background-auth that
  silently swallowed startup errors.
- API clients split into a package (`api/cloud_client.py`, `api/local_client.py`,
  `api/models.py`, `api/exceptions.py`); energy tracking extracted into
  `energy.py`; switches consolidated behind a single `EntityDescription` class.
- Config flow uses modern selectors with translated connection-mode labels
  (en/es/fr); battery-mode select now exposes all modes (backup, expert).
- `manifest.json`: declare `integration_type: hub`.

### Fixed
- Local authentication no longer mislabels a connection failure as an auth
  failure (a transient network issue triggered a spurious reauth instead of a
  retry).
- Battery-mode select previously hid the `backup` and `expert` options.
- Temperature, max-cell-temperature and minimum-discharge use proper unit
  constants; `EntityCategory` is imported from `homeassistant.const`.
- `filter_cookies` DeprecationWarning (now passes a `yarl.URL`).
- IPv6 Envoy hosts are now bracketed in the request URL; discovery prefers an
  IPv4 address, resolves the `.local` hostname to IPv4 (Home Assistant's
  resolver does not handle mDNS), and never overwrites a working host with an
  unreachable IPv6-only mDNS record.

### Removed
- Unused `PyJWT` requirement (JWT is decoded manually).
- Dead code: `_get_session_token`, `_get_envoy_serial`, `get_devices`, and the
  unimplemented local `set_battery_mode` stub.

## [2.35.11] - 2026-04-12

### Fixed
- Fix TypeError on config entry unload (`task.cancel()` returned bool instead of None)

## [2.35.10] - 2026-04-12

### Fixed
- Use dedicated aiohttp session for Enlighten cloud authentication to avoid HA session headers causing HTTP 406
- Restore `login.json?` URL with `user[email]`/`user[password]` form fields matching pyenphase library

## [2.35.9] - 2026-04-12

### Fixed
- Migrate authentication from deprecated `login/login.json` endpoint to `login/login` with form data and session cookies (fixes HTTP 406 Not Acceptable)

## [2.35.8] - 2026-04-07

### Changed
- Enable mypy strict mode with targeted type annotations
- Convert DEVICE_INFO and get_battery_device_info to use DeviceInfo objects
- Use ConfigFlowResult instead of FlowResult for config flow methods

### Added
- Removal/uninstall instructions in README (FR + EN)

### Build
- Pre-commit autoupdate

## [2.35.7] - 2026-02-17

### Changed
- Offset first poll by 5s to desynchronize from official Enphase Envoy integration and reduce 503 errors
- Shorten cloud control cache from 5 minutes to 1 minute for faster UI updates

### Fixed
- Reduce log noise: Envoy connection errors in `get_battery_data` logged at debug level instead of error (coordinator already logs once)

## [2.35.6] - 2026-02-06

### Fixed
- Auto-refresh expired JWT token instead of triggering manual reauth flow (local and cloud modes)

## [2.35.5] - 2026-02-06

### Fixed
- Let `ConfigEntryAuthFailed` propagate through coordinator to trigger Home Assistant reauth flow when JWT token expires

## [2.35.4] - 2026-02-06

### Fixed
- Let `EnvoyAuthError` propagate through `get_battery_data()` to trigger reauth flow when JWT token expires, instead of wrapping it as generic `EnvoyLocalApiError`

## [2.35.3] - 2026-02-06

### Fixed
- Update test to expect error when all Envoy endpoints fail (aligns with v2.35.2 fix)

## [2.35.2] - 2026-02-06

### Fixed
- Properly handle Envoy connection failures: entities now go "unavailable" instead of showing stale/zero values when all endpoints fail (503/timeout)
- Propagate authentication errors (401) to trigger reauth flow when JWT token expires

## [2.35.1] - 2026-02-04

### Changed
- Updated pre-commit hooks to latest versions
- Bump `actions/stale` from 9 to 10 in CI workflow

## [2.35.0] - 2026-01-30

### Added
- Full Quality Scale audit with comprehensive test suite (704 tests, 99% coverage)
- CI workflows: quality checks, HACS validation, stale issues management
- `py.typed` marker for PEP 561 compliance
- Reconfigure and reauth steps in translations (strings.json, en.json, fr.json, es.json)
- Grid mode sensors converted to `SensorDeviceClass.ENUM` with translated states

### Fixed
- French translations: all missing accents restored (~50 corrections)
- Spanish translations: all missing accents restored (~40 corrections)
- Grid mode values normalized (`grid-tied` → `grid_tied`) for translation compatibility
- Envoy 503 response log spam reduced (debug level instead of error)
- OptionsFlow `config_entry` compatibility with older Home Assistant versions
- Proper `loggers` field in manifest.json

### Changed
- Battery number entity platform properly registered via `Platform.NUMBER`
- All loggers use `logging.getLogger(__name__)` pattern
- Generic typing (`dict` instead of `Dict`, `list` instead of `List`)

## [2.34.2] - 2025-01-25

### Fixed
- TypeError on entry unload when `task.cancel()` returns `True` instead of coroutine

## [2.34.1] - 2025-01-25

### Fixed
- PowerMatch switch state now correctly reports from cloud API in hybrid mode
- Filter non-battery devices from individual battery sensors (only IQ Battery 5P devices)

## [2.34.0] - 2025-01-25

### Added
- **Multi-battery support** (Issue #1): Individual battery devices with per-battery sensors
  - Each battery appears as a separate device under "Enphase Battery System"
  - 7 sensors per battery: Temperature, Max Cell Temp, Capacity, Serial, Firmware, SOC, Grid State
  - Proper device hierarchy using `via_device`
- **PowerMatch switch**: New switch entity to control PowerMatch feature
- **Reconfigure options**: Integration settings can now be edited after setup (connection mode, local/cloud config)

### Fixed
- Missing `DOMAIN` import in binary_sensor.py causing `NameError`
- Number entity `BatteryBackupReserveNumber` now properly checks for cloud API availability
- `ConfigEntry` type alias compatibility with Python 3.11
- Test suite updated for `pytest-homeassistant-custom-component` compatibility

### Changed
- **Breaking**: System device identifier changed from `enphase_battery` to `enphase_battery_system`
  - Existing entities may need to be re-added after upgrade
- GitHub Actions updated: `actions/checkout` v6, `actions/setup-python` v6

## [2.33.0] - 2025-01-24

### Performance
- Defer authentication to background task for ultra-fast startup (<2s)
- Entities show as unavailable briefly until first data refresh

## [2.32.0] - 2025-01-19

### Performance
- Optimize startup and memory usage
- Use `__slots__` on entity classes to reduce memory footprint
- Use `TYPE_CHECKING` for lazy imports

## [2.31.0] - 2025-01-18

### Fixed
- Remove invalid `homeassistant` key from manifest.json

### Added
- Improve Home Assistant compliance
- Add French and Spanish translations

## [2.30.1] - 2025-01-18

### Fixed
- Correct `async_on_unload` TypeError on entry unload

## [2.30.0] - 2025-01-17

### Performance
- **Hybrid mode startup optimization**: Eliminated 5-7 second auto-detection delay on every restart
  - Hybrid mode now reuses saved site_id and user_id from config
  - Auto-detection only runs on first setup, then IDs are cached
  - Startup time reduced by 5-7 seconds on every restart after initial setup
  - Matches fast startup behavior of pure cloud mode

## [2.29.0] - 2025-11-12

### Removed
- **MQTT support completely removed** to simplify codebase and improve startup performance
  - Deleted mqtt_client.py (115 lines)
  - Removed MQTT constants and configuration options
  - Removed MQTT setup, reconnection, and shutdown logic
  - Removed get_mqtt_credentials() API method
  - All data now fetched via polling only (cloud: 60s, local: 10s)

### Performance
- **Major performance optimizations** reducing resource usage and API calls:
  - **Batched storage writes**: Energy tracking data saved every 5 minutes instead of every update (10-60s)
    - Reduces disk I/O operations by ~83%
  - **Cloud control state caching**: In hybrid mode, control states cached for 2 minutes instead of fetched every 10s
    - Reduces API calls to Enphase cloud by ~92% (360 → 30 calls/hour)
  - **Smart cache invalidation**: Cache automatically invalidated after user actions (switch/select changes)
    - Ensures immediate UI refresh with real values after control changes
  - **Reduced logging verbosity**: Routine INFO logs converted to DEBUG level
    - Cleaner logs during normal operation (~80% reduction in log noise)

### Changed
- All setup and authentication logs moved to DEBUG level
- Energy tracking restoration logs moved to DEBUG level
- Shutdown logs moved to DEBUG level

## [2.28.0] - 2025-11-11

### Added
- **Automated release workflow** via GitHub Actions
  - Triggers on version tags (v*.*.*)
  - Auto-generates release notes and ZIP archives
  - Publishes releases automatically to GitHub
- **Release helper script** (`scripts/release.sh`)
  - Interactive release creation
  - Automatic version updates in manifest.json and pyproject.toml
  - Color-coded CLI output
- **Code quality tooling**
  - Ruff linter and formatter configuration
  - Pre-commit hooks (optional)
  - MyPy type checking setup
- **CI/CD workflows**
  - Code quality checks (Ruff linting and formatting)
  - Home Assistant Hassfest validation
  - HACS integration validation
  - All checks run on push and pull requests
- **Documentation improvements**
  - CONTRIBUTING.md with development guidelines
  - Release process documentation
  - GitHub Actions status badges in README

### Changed
- All Python code formatted with Ruff for consistency
- Imports organized with isort
- Increased complexity limit for integration-specific logic

### Fixed
- Removed deprecated `domains` key from hacs.json
- Removed unsupported `description` key from manifest.json
- Added GitHub repository topics for better discoverability

## [2.27.3] - 2025-10-31

### Fixed
- Add rate limiting for cloud API error warnings to prevent log spam
- Warning messages now limited to once every 5 minutes when Enphase cloud API has issues
- Integration continues working with local values during cloud API outages

### Changed
- Removed all debug logs from production code
- Cleaner log output focused on important events

## [2.27.2] - 2025-10-31

### Changed
- Removed debug logging from coordinator and API modules
- Improved log clarity by removing verbose fetch messages

## [2.27.1] - 2025-10-31

### Fixed
- Improved optimistic state timing for battery control switches
- Optimistic state now clears before refresh instead of after
- Prevents switches from getting stuck during slow API calls or rapid toggles

## [2.27.0] - 2025-10-31

### Added
- Optimistic state support for "Charge From Grid" switch
- Instant UI feedback for all three battery control switches

### Changed
- All switches now update UI immediately on toggle
- Consistent UX across all battery control switches

## [2.26.3] - 2025-10-31

### Changed
- Removed assumed_state attribute for normal switch visual appearance
- Switches maintain instant feedback without visual indicators

## [2.26.2] - 2025-10-31

### Added
- Optimistic state feedback for dtgControl and rbdControl switches
- Instant visual updates when toggling switches

## [2.26.1] - 2025-10-31

### Fixed
- Fixed dtgControl and rbdControl switches to properly use cloud API
- Fixed coordinator to read switch states from cloud in hybrid mode
- Switches now work correctly in both cloud and hybrid modes

## [2.26.0] - 2025-10-29

### Added
- Reserve Battery Discharge switch (rbdControl)
- Allow Discharge To Grid switch (dtgControl)
- Both switches support cloud and hybrid modes

### Changed
- Improved switch naming for better clarity

## Previous Versions

See git history for changes in versions prior to 2.26.0.

[Unreleased]: https://github.com/foXaCe/enphase-battery/compare/v2.35.7...HEAD
[2.35.7]: https://github.com/foXaCe/enphase-battery/compare/v2.35.6...v2.35.7
[2.35.6]: https://github.com/foXaCe/enphase-battery/compare/v2.35.5...v2.35.6
[2.35.5]: https://github.com/foXaCe/enphase-battery/compare/v2.35.4...v2.35.5
[2.35.4]: https://github.com/foXaCe/enphase-battery/compare/v2.35.3...v2.35.4
[2.35.3]: https://github.com/foXaCe/enphase-battery/compare/v2.35.2...v2.35.3
[2.35.2]: https://github.com/foXaCe/enphase-battery/compare/v2.35.1...v2.35.2
[2.35.1]: https://github.com/foXaCe/enphase-battery/compare/v2.35.0...v2.35.1
[2.35.0]: https://github.com/foXaCe/enphase-battery/compare/v2.34.2...v2.35.0
[2.34.2]: https://github.com/foXaCe/enphase-battery/compare/v2.34.1...v2.34.2
[2.34.1]: https://github.com/foXaCe/enphase-battery/compare/v2.34.0...v2.34.1
[2.34.0]: https://github.com/foXaCe/enphase-battery/compare/v2.33.0...v2.34.0
[2.33.0]: https://github.com/foXaCe/enphase-battery/compare/v2.32.0...v2.33.0
[2.32.0]: https://github.com/foXaCe/enphase-battery/compare/v2.31.0...v2.32.0
[2.31.0]: https://github.com/foXaCe/enphase-battery/compare/v2.30.1...v2.31.0
[2.30.1]: https://github.com/foXaCe/enphase-battery/compare/v2.30.0...v2.30.1
[2.30.0]: https://github.com/foXaCe/enphase-battery/compare/v2.29.0...v2.30.0
[2.29.0]: https://github.com/foXaCe/enphase-battery/compare/v2.28.0...v2.29.0
[2.28.0]: https://github.com/foXaCe/enphase-battery/compare/v2.27.3...v2.28.0
[2.27.3]: https://github.com/foXaCe/enphase-battery/compare/v2.27.2...v2.27.3
[2.27.2]: https://github.com/foXaCe/enphase-battery/compare/v2.27.1...v2.27.2
[2.27.1]: https://github.com/foXaCe/enphase-battery/compare/v2.27.0...v2.27.1
[2.27.0]: https://github.com/foXaCe/enphase-battery/compare/v2.26.3...v2.27.0
[2.26.3]: https://github.com/foXaCe/enphase-battery/compare/v2.26.2...v2.26.3
[2.26.2]: https://github.com/foXaCe/enphase-battery/compare/v2.26.1...v2.26.2
[2.26.1]: https://github.com/foXaCe/enphase-battery/compare/v2.26.0...v2.26.1
[2.26.0]: https://github.com/foXaCe/enphase-battery/releases/tag/v2.26.0
