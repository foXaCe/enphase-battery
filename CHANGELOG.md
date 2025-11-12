# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/foXaCe/enphase-battery/compare/v2.28.0...HEAD
[2.28.0]: https://github.com/foXaCe/enphase-battery/compare/v2.27.3...v2.28.0
[2.27.3]: https://github.com/foXaCe/enphase-battery/compare/v2.27.2...v2.27.3
[2.27.2]: https://github.com/foXaCe/enphase-battery/compare/v2.27.1...v2.27.2
[2.27.1]: https://github.com/foXaCe/enphase-battery/compare/v2.27.0...v2.27.1
[2.27.0]: https://github.com/foXaCe/enphase-battery/compare/v2.26.3...v2.27.0
[2.26.3]: https://github.com/foXaCe/enphase-battery/compare/v2.26.2...v2.26.3
[2.26.2]: https://github.com/foXaCe/enphase-battery/compare/v2.26.1...v2.26.2
[2.26.1]: https://github.com/foXaCe/enphase-battery/compare/v2.26.0...v2.26.1
[2.26.0]: https://github.com/foXaCe/enphase-battery/releases/tag/v2.26.0
