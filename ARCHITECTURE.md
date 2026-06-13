# Architecture — Enphase Battery IQ 5P

This document describes how the integration is structured, how data flows, and
where to extend it.

## Layout

```
custom_components/enphase_battery/
├── __init__.py          # setup/unload/migrate entry; runtime_data wiring
├── coordinator.py       # DataUpdateCoordinator: orchestrates local/cloud/hybrid fetch
├── energy.py            # EnergyTracker: daily counters, 24h consumption, backup time
├── const.py             # constants + DeviceInfo helpers (no HA logic)
├── api/
│   ├── __init__.py      # re-exports the public client surface
│   ├── cloud_client.py  # EnphaseBatteryAPI — Enlighten cloud REST client
│   ├── local_client.py  # EnphaseEnvoyLocalAPI — local Envoy/IQ Gateway client
│   ├── models.py        # BatteryData / BatteryDevice TypedDicts
│   └── exceptions.py    # typed API exceptions (auth vs connection)
├── config_flow.py       # ConfigFlow + OptionsFlow (user/local/cloud/reauth/reconfigure/zeroconf)
├── diagnostics.py       # async_get_config_entry_diagnostics (redacted)
├── system_health.py     # cloud reachability for the System Health panel
├── sensor.py / binary_sensor.py / switch.py / select.py / number.py
├── strings.json + translations/{en,es,fr}.json
├── manifest.json + icons.json
```

## Data flow

```
config entry ──> async_setup_entry (__init__.py)
                   │  creates EnphaseBatteryDataUpdateCoordinator
                   │  await coordinator.async_config_entry_first_refresh()
                   ▼
        coordinator._async_setup()            # once: authenticate + load EnergyTracker
                   │   (EnvoyAuthError/EnphaseBatteryAuthError -> ConfigEntryAuthFailed)
                   │   (connection error          -> UpdateFailed -> ConfigEntryNotReady)
                   ▼
        coordinator._async_update_data()      # every poll
                   │   local_client.get_battery_data()  -> BatteryData   (local / hybrid)
                   │   cloud_client.get_battery_data()   -> BatteryData   (cloud)
                   │   hybrid: merge cached cloud control states into BatteryData
                   │   energy.update(data)               # derived energy values
                   ▼
        coordinator.data : BatteryData
                   │
                   ▼
        entities (CoordinatorEntity) read coordinator.data
```

Connection modes (from `connection_mode` in the entry data):
- **local** — poll the Envoy directly every 10s.
- **cloud** — poll Enlighten every 60s.
- **hybrid** (local + `enable_cloud_control`) — local data, cloud control: the
  switches/select/number write through the cloud client; the coordinator merges
  the cloud control states (cached ~1 min) into the local data.

## Entities

- All entities are `CoordinatorEntity` subclasses; they only read
  `coordinator.data` and never call the API directly (control entities call the
  cloud client through the coordinator's `api`).
- `_attr_has_entity_name = True`; names/labels come from `translations/`.
- **unique_id** = `f"{coordinator.unique_id_prefix}_{key}"` where
  `unique_id_prefix` is the config entry id. Individual batteries use
  `f"{prefix}_battery_{serial}_{key}"`.

## Extension points

**Add a system sensor** — add a `BatterySensorBase` subclass in `sensor.py` and
instantiate it in `async_setup_entry`; add its `translation_key` to the four
translation files.

**Add a switch** — append an `EnphaseBatterySwitchEntityDescription` to the
`SWITCHES` tuple in `switch.py` (give it a `key`, `icon`, and a `set_fn` calling
the cloud client) and add the `key` under `entity.switch` in the translations.

**Add an API call** — add the method to `api/cloud_client.py` or
`api/local_client.py`; return a `BatteryData`-shaped dict (extend
`api/models.py` if you add new keys).

**Add a connection mode / data field** — extend `BatteryData` in
`api/models.py`, populate it in the relevant client, and consume it in the
coordinator or an entity.

## unique_id migration (ConfigEntry version 3)

Legacy `enphase_battery_<key>` unique IDs are rewritten to
`<entry_id>_<key>` by `_async_migrate_unique_ids` in `__init__.py` during
`async_migrate_entry`. The migration is idempotent and covered by tests.

## Discovery & repair issues

- **Zeroconf**: the Envoy advertises `_enphase-envoy._tcp.local.`.
  `async_step_zeroconf` reads its serial (unique_id) and host, aborts/updates if
  already configured, then `async_step_zeroconf_confirm` collects the Enlighten
  credentials needed for a local setup.
- **Repair issue** `control_disabled` is created/cleared by
  `_async_manage_control_issue` in `__init__.py` depending on whether battery
  control is available (cloud or hybrid) or not (local-only).

## Quality gates

- `ruff check` / `ruff format --check`
- `mypy --strict` (clean)
- `pytest --cov-fail-under=98` (currently ~99%)
- `hassfest` + HACS validation (CI: `.github/workflows/`)
