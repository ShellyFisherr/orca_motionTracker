import json
import time

from pathlib import Path
from datetime import datetime
from statistics import median

from orca_motionTracker.Input.udp_receiver import FlexionUDPReceiver
from orca_motionTracker.Processing.finger_mapping import FINGERS

SAMPLE_COUNT = 120

COLLECTION_TIMEOUT = 15.0

MIN_CALIBRATION_RANGE = 0.10

PROJECT_ROOT = Path(__file__).resolve().parents[3]

CALIBRATION_FILE = (PROJECT_ROOT / "config" / "hand_calibration.json")


def collect_samples(receiver, pose_name, sample_count):

    samples = []

    last_sequence = receiver.get_latest_sequence()

    print(f"\nCollecting {pose_name} hand measurements...")
    print(f"Required samples: {sample_count}")

    start_time = time.monotonic()

    while len(samples) < sample_count:
        flexion = receiver.get_latest()

        sequence = receiver.get_latest_sequence()

        if (flexion is not None
            and sequence is not None
            and sequence != last_sequence):

            samples.append(flexion.copy())

            last_sequence = sequence

            print(f"\rSamples collected: "
                  f"{len(samples)}/{sample_count}",
                  end="",
                  flush=True)

        if time.monotonic() - start_time > COLLECTION_TIMEOUT:
            raise TimeoutError(
                f"Could not cleect {sample_count} samples "
                f"for {pose_name} hand withing "
                f"{COLLECTION_TIMEOUT} seconds."
            )    
        time.sleep(0.001)

    print("\nCollection complete.")
    return samples


def calculate_reference(samples):
    reference = {}

    for finger in FINGERS:
        measurements = [sample[finger] for sample in samples]

        reference[finger] = median(measurements)

    return reference


def validate_calibration(open_reference, closed_reference):

    valid = True

    scales = {}
    offsets = {}

    print("\nChecking calibration ranges")

    for finger in FINGERS:

        open_value = open_reference[finger]
        closed_value = closed_reference[finger]

        difference = closed_value - open_value

        print(
            f"{finger:>7}: "
            f"open={open_value:.4f}, "
            f"closed={closed_value:.4f}, "
            f"range={difference:.4f}"
        )

        if difference < MIN_CALIBRATION_RANGE:

            print(
                f"WARNING: {finger} has an insufficient calibration range."
            )

            valid = False

        else:

            scales[finger] = 1.0 / difference
            offsets[finger] = -open_value * scales[finger]

    return valid, scales, offsets

def save_calibration(open_reference, closed_reference, scales, offsets):

    calibration = {
        "calibration_version": 2,

        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),

        "sample_count": SAMPLE_COUNT,

        "method": "median",

        "fingers": {}
    }

    for finger in FINGERS:

        calibration["fingers"][finger] = {
            "open": open_reference[finger],

            "closed": closed_reference[finger],

            "scale": scales[finger],

            "offset": offsets[finger]
        }

    CALIBRATION_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(CALIBRATION_FILE, "w") as file:

        json.dump(
            calibration,
            file,
            indent=4
        )

    print("\nCalibration successfully saved!")
    print(f"Location: {CALIBRATION_FILE}")


def main():

    receiver = FlexionUDPReceiver(
        host = "0.0.0.0",
        port = 5010,
        timeout=0.25
    )

    try:
        print("\n==================================")
        print("         HAND CALIBRATION")
        print("==================================")

        print("\nWaiting for SenseGlove data...")

        while receiver.get_latest() is None:
            time.sleep(0.01)

        print("SenseGlove connected. Data Received.")


        input("\nFully OPEN your hand and keep it still.\n"
              "Press ENTER when you are ready to start calibration...")

        open_samples = collect_samples(
            receiver,
            "OPEN",
            SAMPLE_COUNT
        )

        open_reference = calculate_reference(open_samples)

        input("\n Fully CLOSE your hand and keep it still\n"
              "Press ENTER when you are ready to start calibration...")

        closed_samples = collect_samples(
            receiver,
            "CLOSED",
            SAMPLE_COUNT
        )

        closed_reference = calculate_reference(closed_samples)

        print("\n================================")
        print("       CALIBRATION  RESULTS")
        print("================================")

        valid, scales, offsets = validate_calibration(open_reference, closed_reference)

        if not valid:
            print("\n Calibration rejected. Please repeat the calibration.")
            return

        save_calibration(open_reference, closed_reference, scales, offsets)

    except KeyboardInterrupt:
        print("\nCalibration Interupted")

    except TimeoutError as error:
        print(f"\nCalibration failed: {error}")

    finally:

        print("\nClosing UDP Receiver...")
        receiver.close()


if __name__ == "__main__":
    main()
        
