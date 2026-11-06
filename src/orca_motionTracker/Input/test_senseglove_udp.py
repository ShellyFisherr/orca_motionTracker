import socket
import time

from orca_motionTracker.Input.senseglove_udp import SenseGloveUDPReceiver

HOST = "192.168.216.10"
PORT = 5010

def create_test_packet(sequence: int) -> bytes:
    values = [
        str(sequence),
        str(int(time.monotonic()*1000)),
        "5",
    ]

    for finger in range(5):
        values.append("4")

        for joint in range(4):
            x = finger * 10 + joint
            y = finger * 5 + joint
            z = finger * 2 + joint

            values.extend([
                str(float(x)),
                str(float(y)),
                str(float(z)),
            ])

    return ",".join(values).encode("ascii")

def main():

    receiver = SenseGloveUDPReceiver(
        host=HOST,
        port=PORT,
        timeout=0.05,
    )

    sender = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        for sequence in range(10):
            packet = create_test_packet(sequence)

            sender.sendto(
                packet,
                (HOST, PORT)
            )

            time.sleep(0.01)

            frame = receiver.receive()

            if frame is None:
                print("No packet received")
                continue

            print(f"\nSequence: {frame.sequence}")
            print(f"Elapsed: {frame.elapsed_ms} ms")
            print(f"finger count: {len(frame.positions_mm)}")

            for index, finger in enumerate(frame.positions_mm):
                print(
                    f"finger {index}: "
                    f"shape={finger.shape}, "
                    f"first joint={finger[0]}"
                )

    finally:
        sender.close()
        receiver.close()


if __name__ == "__main__":
    main()