# Deye Microinverter — Home Assistant Custom Integration

Local-polling integration for Deye Solar microinverters. Communicates directly
over the Modbus-TCP protocol exposed by the inverter's built-in logger on port 8899.

## Installation

1. Copy `custom_components/deye_microinverter/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for
   **Deye Microinverter**.

## Configuration

| Field         | Description                                      | Default |
|---------------|--------------------------------------------------|---------|
| IP Address    | Local IP address of the inverter                 | —       |
| Port          | Modbus TCP port of the logger                    | 8899    |
| Serial Number | 10-digit logger serial number (e.g. 4173111111)  | —       |

Each configured inverter appears as a separate device with two entities:

| Entity               | Type   | Unit | Description                              |
|----------------------|--------|------|------------------------------------------|
| Power Generation     | Sensor | W    | Current AC output power, updated every 30 s |
| Power Limit          | Number | %    | Active power limit (1–100 %), readable and writable |

## CLI — testing without Home Assistant

The package includes a command-line entry point for verifying communication
with the inverter before or during integration setup.

**Requirements:** `libscrc` must be installed (`pip install libscrc`).

```
python -m custom_components.deye_microinverter \
    --host HOST \
    [--port PORT] \
    --serial SERIAL \
    COMMAND
```

| Argument   | Description                                    | Default |
|------------|------------------------------------------------|---------|
| `--host`   | Inverter IP address                            | —       |
| `--port`   | Modbus TCP port                                | 8899    |
| `--serial` | Logger serial number (integer, e.g. 4173111111)| —       |

### Commands

#### `get-generation` — read current output power

```bash
python -m custom_components.deye_microinverter \
    --host 192.168.0.101 --serial 4173111111 \
    get-generation
```

```
Power generation: 342.5 W
```

#### `get-limit` — read active power limit

```bash
python -m custom_components.deye_microinverter \
    --host 192.168.0.101 --serial 4173111111 \
    get-limit
```

```
Power limit: 80 %
```

#### `set-limit VALUE` — write active power limit

Retries up to 10 times on failure, waits 5 s for the inverter to settle after
a successful write, then reads back the register to confirm.

```bash
python -m custom_components.deye_microinverter \
    --host 192.168.0.101 --serial 4173111111 \
    set-limit 80
```

```
Setting power limit to 80 % (up to 10 attempts)...
OK (attempt 1); waiting 5s for inverter to settle...
Confirmed power limit: 80 %
```

All commands exit with code `0` on success and `1` on failure.
