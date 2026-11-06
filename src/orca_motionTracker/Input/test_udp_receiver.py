
import time

from orca_motionTracker.Input.udp_receiver import FlexionUDPReceiver


def main():

    receiver = FlexionUDPReceiver(port=5010)

    try:
        print("Waiting for glove data...")

        last_statistics_time = time.monotonic()

        while True:

            flexion = receiver.get_latest()

            if flexion is not None:
                print(f"\r{flexion}", end="", flush=True)

            else:
                print("\rWaiting for glove data...          ", end="", flush=True)

            # Display communication statistics every second
            if time.monotonic() - last_statistics_time >= 1.0:

                stats = receiver.get_statistics()

                print(f"\n{stats}")

                last_statistics_time = time.monotonic()

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nUser interrupted the test.")

    finally:
        print("\nClosing UDP receiver...")
        receiver.close()


if __name__ == "__main__":
    main()
