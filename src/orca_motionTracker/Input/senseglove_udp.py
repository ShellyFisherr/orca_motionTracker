"""UDP receiver for windows SenseGlove Nova 2 publisher"""

from __future__ import annotations

import socket

from dataclasses import dataclass

import numpy as np

@dataclass
class SenseGloveFrame:
    sequence: int
    elapsed_ms: int
    positions_mm: list[np.ndarray]

class SenseGloveUDPReceiver:
    def __init__(
            self,
            host: str = "0.0.0.0",
            port: int = 5010,
            timeout: float = 0.05,):

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(timeout)

        print(f"Listening for SenseGlove UDP on {host}:{port}")

    @staticmethod
    def decode_packet(packet: bytes) -> SenseGloveFrame:
        try:
            values = packet.decode("ascii").strip().split(",")

            if len(values) < 3:
                raise ValueError("Packet too short")

            sequence = int(values[0])
            elapsed_ms = int(values[1])
            finger_count = int (values[2])

            if finger_count <= 0 or finger_count > 10:
                raise ValueError(f"Invalid finger count: {finger_count}")

            index = 3
            fingers = []

            for finger in range(finger_count):
                if index >= len(values):
                    raise ValueError("Missing joint count")

                joint_count = int(values[index])
                index += 1

                if joint_count != 4:
                    raise ValueError(
                        f"Finger {finger}: "
                        f"expected 4 joints, received {joint_count}"
                    )

                required_values = joint_count * 3

                if index + required_values > len(values):
                    raise ValueError("Incomplete joint coordinates")

                coordinates = np.asarray(
                    values[index:index + required_values],
                    dtype=np.float32,).reshape(joint_count, 3)

                if not np.all(np.isfinite(coordinates)):
                    raise ValueError("Non-finite joint coordinate")

                fingers.append(coordinates)
                index += required_values

            if index != len(values):
                raise ValueError("Unexpected extra packet values")

            return SenseGloveFrame(
                sequence=sequence,
                elapsed_ms=elapsed_ms,
                positions_mm=fingers,
            )

        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid SenseGlove packet: {exc}") from exc

    def receive(self) -> SenseGloveFrame | None:
        try:
            packet, address = self.socket.recvfrom(4096)
        except socket.timeout:
            return None

        frame = self.decode_packet(packet)

        return frame

    def close(self):
        self.socket.close()