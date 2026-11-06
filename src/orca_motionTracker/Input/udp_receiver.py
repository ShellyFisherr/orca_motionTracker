import socket
import time
import math


class FlexionUDPReceiver:
    def __init__(self, host = "0.0.0.0", port = 5010, timeout = 0.25):

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.sock.bind((host, port))

        self.sock.setblocking(False)

        self.timeout = timeout
        self.last_data_time = None
        self.latest_fexion = None

        self.last_sequence = None

        self.missing_packets = 0
        self.out_of_order_packets = 0
        self.duplicate_packets = 0
        self.received_packets = 0
        self.invalid_packets = 0
        self.latest_sequence = 0

        print(f" Listening for UDP packets on {host}:{port} with a timeout of {timeout} seconds.")

    def get_latest(self):

        while True:
            try:
                data, address = self.sock.recvfrom(1024)

            except BlockingIOError:
                break

            try:
                parts = data.decode("utf-8").strip().split(",")



                if len(parts) != 6:
                    print(f"Received data with unexpected length: {len(parts)}. Expected 6 values.")
                    continue

                sequence = int(parts[0])
                flexion = [float(value) for value in parts[1:]]


                if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in flexion):
                    print(f"Received data with out-of-range values. Expected values between 0.0 and 1.0.")
                    continue

                if self.last_sequence is None:
                    self.last_sequence = sequence
                    self.latest_sequence = sequence

                else:
                    if sequence == self.last_sequence:
                        self.duplicate_packets += 1
                        continue

                    if sequence < self.last_sequence:
                        self.out_of_order_packets += 1
                        continue

                    if sequence > self.last_sequence + 1:
                        self.missing_packets += sequence - self.last_sequence - 1

                    self.last_sequence = sequence
                    self.latest_sequence = sequence

                self.received_packets += 1

                self.latest_flexion = {
                    "thumb": flexion[0],
                    "index": flexion[1],
                    "middle": flexion[2],
                    "ring": flexion[3],
                    "pinky": flexion[4]
                }

                self.last_data_time = time.monotonic()


            except (UnicodeDecodeError, ValueError) as error:
                print(f"Received invalid UDP packer: {error}")
                self.invalid_packets += 1
                continue

        if self.last_data_time is None:
            return None

        age = time.monotonic() - self.last_data_time

        if age > self.timeout:
            return None

        return self.latest_flexion

    def get_statistics(self):
        return {
            "received": self.received_packets,
            "missing": self.missing_packets,
            "out_of_order": self.out_of_order_packets,
            "duplicates": self.duplicate_packets,
            "invalid": self.invalid_packets
        }

    def get_latest_sequence(self):
        return self.latest_sequence

    def close(self):
        self.sock.close()
