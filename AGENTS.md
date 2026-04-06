# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

Install the single runtime dependency:
```bash
pip install libscrc
```

Test inverter communication without Home Assistant:
```bash
python -m custom_components.deye_microinverter --host <IP> --serial <SERIAL> get-generation
python -m custom_components.deye_microinverter --host <IP> --serial <SERIAL> get-limit
python -m custom_components.deye_microinverter --host <IP> --serial <SERIAL> set-limit <1-100>
```

There is no test suite and no build step. The integration is loaded directly by Home Assistant from the `custom_components/` directory.

## Architecture

### Protocol layer — `inverter.py`

`DeyeModbus` is a **synchronous** class; all methods block on TCP I/O and must be called from a thread-pool executor (`hass.async_add_executor_job`). Never call it directly from async code.

The wire format is Modbus RTU wrapped in a Deye-proprietary TCP envelope (start byte `0xA5`, end byte `0x15`). The logger serial number is embedded in the outer frame — mismatches produce a 29-byte error response rather than a normal reply. CRC is computed with `libscrc.modbus()`.

Key register addresses are constants in `inverter.py`:
- `REG_POWER_GENERATION = 86` — raw value is 0.1 W units (divide by 10)
- `REG_POWER_LIMIT = 40` — value is percent (1–100)

### Coordinator — `coordinator.py`

`DeyeCoordinator` polls both registers every 30 seconds. An empty dict from `read_registers` (connection failure) raises `UpdateFailed`, which HA uses to mark all entities unavailable. There is no retry on read — the next poll cycle recovers automatically.

### Entities

| File | Entity | HA type | Writable |
|------|--------|---------|----------|
| `sensor.py` | Power Generation | `SensorEntity` | no |
| `number.py` | Power Limit | `NumberEntity` | yes |

Writing the power limit (`number.py`) runs `_set_power_limit` in an executor with up to 10 retries (1 s between attempts) and a 5 s settle delay after success, then triggers a coordinator refresh.

### Entry lifecycle — `__init__.py`

`async_setup_entry` constructs `DeyeModbus` → `DeyeCoordinator` → calls `async_config_entry_first_refresh()`. If the inverter is unreachable at setup time, `ConfigEntryNotReady` is raised and HA retries automatically. The coordinator instance is stored in `hass.data[DOMAIN][entry.entry_id]` and retrieved by each platform's `async_setup_entry`.

### CLI — `__main__.py`

Only executed via `python -m custom_components.deye_microinverter`. Never imported by HA. Reuses `DeyeModbus` directly (no coordinator) and mirrors the same retry/settle logic as the number entity for `set-limit`.
