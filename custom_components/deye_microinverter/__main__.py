"""CLI entry point for testing inverter communication.

Usage:
    python -m custom_components.deye_microinverter --host HOST [--port PORT] --serial SERIAL COMMAND

Commands:
    get-generation          Read current AC output power (W)
    get-limit               Read active power limit (%)
    set-limit VALUE         Write active power limit (1–100 %)

Examples:
    python -m custom_components.deye_microinverter --host 192.168.0.101 --serial 4173111111 get-generation
    python -m custom_components.deye_microinverter --host 192.168.0.101 --serial 4173111111 get-limit
    python -m custom_components.deye_microinverter --host 192.168.0.101 --serial 4173111111 set-limit 80
"""

import argparse
import sys
from time import sleep

from .inverter import DeyeModbus, REG_POWER_GENERATION, REG_POWER_LIMIT

_WRITE_RETRIES = 10
_RETRY_DELAY_S = 1
_POST_WRITE_SETTLE_S = 5


def cmd_get_generation(inverter: DeyeModbus) -> int:
    regs = inverter.read_registers(REG_POWER_GENERATION, REG_POWER_GENERATION)
    if not regs:
        print("ERROR: no response from inverter", file=sys.stderr)
        return 1
    value = int.from_bytes(regs[REG_POWER_GENERATION], "big") / 10
    print(f"Power generation: {value} W")
    return 0


def cmd_get_limit(inverter: DeyeModbus) -> int:
    regs = inverter.read_registers(REG_POWER_LIMIT, REG_POWER_LIMIT)
    if not regs:
        print("ERROR: no response from inverter", file=sys.stderr)
        return 1
    value = int.from_bytes(regs[REG_POWER_LIMIT], "big")
    print(f"Power limit: {value} %")
    return 0


def cmd_set_limit(inverter: DeyeModbus, value: int) -> int:
    if not 1 <= value <= 100:
        print("ERROR: power limit must be between 1 and 100", file=sys.stderr)
        return 1

    print(f"Setting power limit to {value} % (up to {_WRITE_RETRIES} attempts)...")
    for attempt in range(1, _WRITE_RETRIES + 1):
        try:
            if inverter.write_register_uint(REG_POWER_LIMIT, value):
                print(f"OK (attempt {attempt}); waiting {_POST_WRITE_SETTLE_S}s for inverter to settle...")
                sleep(_POST_WRITE_SETTLE_S)
                # Read back to confirm
                regs = inverter.read_registers(REG_POWER_LIMIT, REG_POWER_LIMIT)
                if regs:
                    actual = int.from_bytes(regs[REG_POWER_LIMIT], "big")
                    print(f"Confirmed power limit: {actual} %")
                return 0
        except Exception as err:
            print(f"Attempt {attempt}/{_WRITE_RETRIES} failed: {err}", file=sys.stderr)
        if attempt < _WRITE_RETRIES:
            sleep(_RETRY_DELAY_S)

    print("ERROR: failed to set power limit after all retries", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deye Microinverter CLI — test get/set functionality"
    )
    parser.add_argument("--host", required=True, help="Inverter IP address")
    parser.add_argument("--port", type=int, default=8899, help="Modbus TCP port (default: 8899)")
    parser.add_argument("--serial", required=True, type=int, help="Logger serial number (e.g. 4173111111)")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    sub.add_parser("get-generation", help="Read current AC output power (W)")
    sub.add_parser("get-limit", help="Read active power limit (%%)")
    set_p = sub.add_parser("set-limit", help="Write active power limit (1–100 %%)")
    set_p.add_argument("value", type=int, metavar="VALUE", help="New limit in percent")

    args = parser.parse_args()
    inverter = DeyeModbus(args.host, args.port, args.serial)

    if args.command == "get-generation":
        return cmd_get_generation(inverter)
    if args.command == "get-limit":
        return cmd_get_limit(inverter)
    if args.command == "set-limit":
        return cmd_set_limit(inverter, args.value)

if __name__ == "__main__":
    sys.exit(main())
