"""Synchronous Modbus-over-TCP client for Deye Solar microinverters.

Protocol reference: https://github.com/jlopez77/DeyeInverter
Register map: https://github.com/jedie/inverter-connect/blob/main/inverter/definitions/deye_2mppt.yaml
"""

import logging
import socket

_LOGGER = logging.getLogger(__name__)

# Modbus register addresses
REG_YIELD_TODAY_FIRST = 60  # daily yield, unit 0.1 kWh (range start)
REG_YIELD_TODAY = 60        # daily yield, unit 0.1 kWh
REG_YIELD_TOTAL = 62        # total yield, unit 0.1 kWh
REG_YIELD_TODAY_LAST = 62   # daily/total yield range end
REG_AC_VOLTAGE_FIRST = 73   # AC voltage range start
REG_AC_VOLTAGE = 73         # AC voltage, unit 0.1 V
REG_AC_CURRENT = 74         # AC current, unit 0.1 A
REG_AC_FREQUENCY = 79       # AC frequency, unit 0.01 Hz
REG_AC_VOLTAGE_LAST = 79    # AC voltage/current/frequency range end
REG_POWER_GENERATION = 86   # current AC output power, unit 0.1 W
REG_POWER_LIMIT = 40        # active power limit, unit % (older models)
REG_POWER_LIMIT_G4 = 53     # active power limit, unit 0.01% (G4/newer models; 10000 = 100%)


class DeyeModbus:
    """Simplified Modbus over TCP for Deye Solar microinverters.

    All methods are blocking and intended to be called from a thread-pool
    executor (via hass.async_add_executor_job).
    """

    def __init__(self, ip_address: str, port: int, serial_number: int) -> None:
        self._ip_address = ip_address
        self._port = port
        self._serial_number = serial_number
        self._reachable = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_registers(self, first_reg: int, last_reg: int) -> dict[int, bytes]:
        """Read one or more consecutive holding registers.

        Returns a dict mapping register address → 2-byte value, or an
        empty dict when communication fails.
        """
        modbus_frame = self._build_read_request(first_reg, last_reg)
        modbus_frame += self._crc(modbus_frame)

        response = self._send_request(modbus_frame)
        if response is None:
            return {}
        return self._parse_read_response(response, first_reg, last_reg)

    def write_register_uint(self, reg_address: int, reg_value: int) -> bool:
        """Write a single holding register from an unsigned integer value."""
        return self.write_registers(
            reg_address, [reg_value.to_bytes(2, "big", signed=False)]
        )

    def write_registers(
        self, reg_address: int, reg_values: list[bytes]
    ) -> bool:
        """Write one or more consecutive holding registers."""
        modbus_frame = self._build_write_request(reg_address, reg_values)
        modbus_frame += self._crc(modbus_frame)

        response = self._send_request(modbus_frame)
        if response is None:
            return False
        return self._parse_write_response(response, reg_address, reg_values)

    # ------------------------------------------------------------------
    # Modbus frame helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _modbus_crc(frame: bytes | bytearray) -> int:
        crc = 0xFFFF
        for byte in frame:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    @staticmethod
    def _crc(frame: bytearray) -> bytearray:
        crc = DeyeModbus._modbus_crc(frame)
        return bytearray([crc & 0xFF, crc >> 8])

    @staticmethod
    def _build_read_request(first_reg: int, last_reg: int) -> bytearray:
        reg_count = last_reg - first_reg + 1
        return bytearray.fromhex("0103{:04x}{:04x}".format(first_reg, reg_count))

    @staticmethod
    def _build_write_request(
        reg_address: int, reg_values: list[bytes]
    ) -> bytearray:
        result = bytearray.fromhex(
            "0110{:04x}{:04x}{:02x}".format(
                reg_address, len(reg_values), len(reg_values) * 2
            )
        )
        for v in reg_values:
            result.extend(v)
        return result

    @staticmethod
    def _parse_read_response(
        frame: bytes, first_reg: int, last_reg: int
    ) -> dict[int, bytes]:
        reg_count = last_reg - first_reg + 1
        expected_data_len = 3 + reg_count * 2  # addr + fn + byte_count + data
        if len(frame) < expected_data_len + 2:
            _LOGGER.warning("Modbus read response too short: %d bytes", len(frame))
            return {}
        actual_crc = int.from_bytes(
            frame[expected_data_len: expected_data_len + 2], "little"
        )
        expected_crc = DeyeModbus._modbus_crc(frame[:expected_data_len])
        if actual_crc != expected_crc:
            _LOGGER.warning(
                "Modbus read CRC mismatch: expected %04x, got %04x",
                expected_crc,
                actual_crc,
            )
            return {}
        return {
            first_reg + i: frame[3 + i * 2: 5 + i * 2] for i in range(reg_count)
        }

    @staticmethod
    def _parse_write_response(
        frame: bytes, reg_address: int, reg_values: list[bytes]
    ) -> bool:
        expected_data_len = 6
        if len(frame) < expected_data_len + 2:
            _LOGGER.warning(
                "Modbus write response too short: %d bytes", len(frame)
            )
            return False
        actual_crc = int.from_bytes(
            frame[expected_data_len: expected_data_len + 2], "little"
        )
        expected_crc = DeyeModbus._modbus_crc(frame[:expected_data_len])
        if actual_crc != expected_crc:
            _LOGGER.warning(
                "Modbus write CRC mismatch: expected %04x, got %04x",
                expected_crc,
                actual_crc,
            )
            return False
        returned_address = int.from_bytes(frame[2:4], "big")
        returned_count = int.from_bytes(frame[4:6], "big")
        if returned_address != reg_address:
            _LOGGER.warning(
                "Write response address mismatch: expected %d, got %d",
                reg_address,
                returned_address,
            )
            return False
        if returned_count != len(reg_values):
            _LOGGER.warning(
                "Write response count mismatch: expected %d, got %d",
                len(reg_values),
                returned_count,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Outer (logger) frame helpers
    # ------------------------------------------------------------------

    def _build_outer_frame(self, modbus_frame: bytearray) -> bytearray:
        """Wrap a Modbus RTU frame in the Deye logger TCP envelope."""
        # Serial number bytes (little-endian, variable length)
        sn_bytes = bytearray.fromhex("{:10x}".format(self._serial_number))
        sn_bytes.reverse()

        frame = bytearray()
        frame += bytearray.fromhex("A5")               # start
        frame += (13 + len(modbus_frame) + 2).to_bytes(2, "little")  # data length
        frame += bytearray.fromhex("1045")             # control code
        frame += bytearray.fromhex("0000")             # SN prefix
        frame += sn_bytes                               # logger serial number
        frame += bytearray.fromhex("020000000000000000000000000000")  # data field
        frame += modbus_frame
        frame += bytearray.fromhex("00")               # checksum placeholder
        frame += bytearray.fromhex("15")               # end

        frame[-2] = sum(frame[1:-2]) & 0xFF
        return frame

    def _extract_modbus_frame(self, frame: bytes | None) -> bytes | None:
        """Strip the Deye logger envelope and return the inner Modbus frame."""
        if not frame:
            return None
        if frame[:3] == b"AT+":
            _LOGGER.error(
                "Inverter at %s responded with AT command; wrong protocol mode",
                self._ip_address,
            )
            return None
        if len(frame) == 29:
            # Error response — no inner Modbus payload
            self._log_error_response(frame)
            return None
        if len(frame) < 33:  # 29-byte envelope + at least 4 bytes of Modbus
            _LOGGER.warning(
                "Response frame too short: %d bytes", len(frame)
            )
            return None
        if frame[0] != 0xA5 or frame[-1] != 0x15:
            _LOGGER.warning("Response frame has invalid start/end bytes")
            return None
        return frame[25:-2]

    @staticmethod
    def _log_error_response(frame: bytes) -> None:
        error_code = frame[25]
        if error_code == 0x05:
            _LOGGER.error(
                "Inverter rejected request: Modbus device address mismatch"
            )
        elif error_code == 0x06:
            _LOGGER.error(
                "Inverter rejected request: logger serial number mismatch — "
                "check the serial number in your configuration"
            )
        else:
            _LOGGER.warning(
                "Inverter returned unknown error code: %02x", error_code
            )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _send_request(self, modbus_frame: bytearray) -> bytes | None:
        req_frame = self._build_outer_frame(modbus_frame)
        resp_frame = self._send_tcp(req_frame)
        return self._extract_modbus_frame(resp_frame)

    def _send_tcp(self, req_frame: bytearray) -> bytes | None:
        try:
            sock = socket.create_connection(
                (self._ip_address, self._port), timeout=5
            )
        except OSError as err:
            if self._reachable:
                _LOGGER.warning(
                    "Cannot connect to inverter at %s:%d: %s",
                    self._ip_address,
                    self._port,
                    err,
                )
                self._reachable = False
            return None

        if not self._reachable:
            _LOGGER.info("Reconnected to inverter at %s", self._ip_address)
            self._reachable = True

        try:
            sock.sendall(req_frame)
            for _ in range(5):
                try:
                    data = sock.recv(1024)
                    if data:
                        return data
                    _LOGGER.debug("Empty response from inverter at %s", self._ip_address)
                except socket.timeout:
                    _LOGGER.debug("Receive timeout from inverter at %s", self._ip_address)
                except OSError as err:
                    _LOGGER.warning(
                        "Socket error from inverter at %s: %s", self._ip_address, err
                    )
                    return None
        finally:
            sock.close()

        _LOGGER.warning(
            "No valid response from inverter at %s after retries", self._ip_address
        )
        return None
