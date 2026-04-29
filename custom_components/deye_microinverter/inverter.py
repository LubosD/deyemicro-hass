"""Synchronous Modbus-over-TCP client for Deye Solar microinverters.

Protocol reference: https://github.com/jlopez77/DeyeInverter
Register map: https://github.com/jedie/inverter-connect/blob/main/inverter/definitions/deye_2mppt.yaml
"""

import logging
import socket

_LOGGER = logging.getLogger(__name__)

# Modbus register addresses
REG_YIELD_TODAY_FIRST = 60   # daily yield, unit 0.1 kWh (range start)
REG_YIELD_TODAY = 60         # daily yield, unit 0.1 kWh
REG_YIELD_TOTAL = 63         # total yield, low word of 32-bit value, unit 0.1 kWh
REG_YIELD_TOTAL_HIGH = 64    # total yield, high word of 32-bit value
REG_YIELD_TODAY_LAST = 64    # yield register range end
REG_AC_VOLTAGE_FIRST = 73   # AC voltage range start
REG_AC_VOLTAGE = 73         # AC voltage, unit 0.1 V
REG_AC_CURRENT = 74         # AC current, unit 0.1 A
REG_AC_FREQUENCY = 79       # AC frequency, unit 0.01 Hz
REG_AC_VOLTAGE_LAST = 79    # AC voltage/current/frequency range end
REG_POWER_GENERATION = 86   # current AC output power, unit 0.1 W
REG_POWER_LIMIT = 40        # active power limit, unit %


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
        self._sock: socket.socket | None = None

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

    def close(self) -> None:
        """Close the persistent TCP connection."""
        self._disconnect()

    def _disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _ensure_connected(self) -> socket.socket:
        if self._sock is None:
            sock = socket.create_connection((self._ip_address, self._port), timeout=5)
            sock.settimeout(5)
            self._sock = sock
            if not self._reachable:
                _LOGGER.info("Reconnected to inverter at %s", self._ip_address)
                self._reachable = True
        return self._sock

    def _send_request(self, modbus_frame: bytearray) -> bytes | None:
        req_frame = self._build_outer_frame(modbus_frame)
        resp_frame = self._send_tcp(req_frame)
        return self._extract_modbus_frame(resp_frame)

    # SolarmanV5 keepalive/heartbeat control code (0x4710 little-endian)
    _CTRL_KEEPALIVE = b"\x10\x47"

    def _recv_outer_frame(self, sock: socket.socket) -> bytes | None:
        """Read exactly one complete SolarmanV5 outer frame from the socket.

        Buffers partial TCP reads until the full frame (determined by the
        2-byte length field at bytes 1-2) is assembled.  Raises OSError /
        socket.timeout so the caller can decide whether to reconnect.
        """
        buf = bytearray()

        # Phase 1: collect the start byte + 2-byte length field.
        while len(buf) < 3:
            chunk = sock.recv(1024)
            if not chunk:
                return None
            buf.extend(chunk)

        if buf[0] != 0xA5:
            return bytes(buf)  # unexpected; _extract_modbus_frame will log it

        payload_len = int.from_bytes(buf[1:3], "little")
        # Total = start(1) + length_field(2) + payload + checksum(1) + end(1)
        total_len = payload_len + 5

        if total_len > 512:
            _LOGGER.warning(
                "Implausible frame length %d from %s", total_len, self._ip_address
            )
            return bytes(buf)

        # Phase 2: collect the remainder of the frame.
        while len(buf) < total_len:
            chunk = sock.recv(total_len - len(buf))
            if not chunk:
                _LOGGER.warning(
                    "Connection closed mid-frame (%d/%d bytes) from %s",
                    len(buf),
                    total_len,
                    self._ip_address,
                )
                break
            buf.extend(chunk)

        return bytes(buf)

    def _try_send_tcp(self, req_frame: bytearray) -> bytes | None:
        """Attempt one send+receive cycle on the current (or newly opened) connection.

        Returns None and sets self._sock to None if the connection was lost,
        signalling the caller to retry on a fresh socket.
        """
        try:
            sock = self._ensure_connected()
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

        try:
            sock.sendall(req_frame)
        except OSError as err:
            _LOGGER.debug("Send failed, will reconnect: %s", err)
            self._disconnect()
            return None

        for _ in range(5):
            try:
                frame = self._recv_outer_frame(sock)
            except socket.timeout:
                _LOGGER.debug("Receive timeout from inverter at %s", self._ip_address)
                continue
            except OSError as err:
                _LOGGER.warning(
                    "Socket error from inverter at %s: %s", self._ip_address, err
                )
                self._disconnect()
                return None

            if not frame:
                _LOGGER.debug("Empty response from inverter at %s", self._ip_address)
                continue

            # Silently discard keepalive/heartbeat frames and keep waiting.
            if len(frame) >= 5 and frame[3:5] == self._CTRL_KEEPALIVE:
                _LOGGER.debug("Discarding keepalive frame from %s", self._ip_address)
                continue

            return frame

        _LOGGER.warning(
            "No valid response from inverter at %s after retries", self._ip_address
        )
        return None

    def _send_tcp(self, req_frame: bytearray) -> bytes | None:
        response = self._try_send_tcp(req_frame)
        if response is not None:
            return response
        # Socket was dropped (stale connection) — retry once with a fresh connection.
        if self._sock is None:
            response = self._try_send_tcp(req_frame)
        return response
