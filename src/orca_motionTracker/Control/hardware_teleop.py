

from __future__ import annotations

import argparse
import json
import time
import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from orca_core import OrcaJointPositions
from orca_core.utils.cli import (
    add_hand_arguments,
    connect_hand,
    create_hand_from_args,
    shutdown_hand,
)

from orca_motionTracker.Input.calibrate_hand import CALIBRATION_FILE
from orca_motionTracker.Input.udp_receiver import FlexionUDPReceiver
from orca_motionTracker.Processing.finger_mapping import FINGERS

FINGER_JOINTS: dict[str, list[str]] = {
    "thumb": ["thumb_cmc", "thumb_mcp"],
    "index": ["index_mcp", "index_pip"],
    "middle": ["middle_mcp", "middle_pip"],
    "ring": ["ring_mcp", "ring_pip"],
    "pinky": ["pinky_mcp", "pinky_pip"],
}

OPEN_AT_NEUTRAL_JOINTS: set[str] = {
    "index_mcp", "index_pip",
    "middle_mcp", "middle_pip",
    "ring_mcp", "ring_pip",
    "pinky_mcp", "pinky_pip",
}

THUMB_ABD_JOINT = "thumb_abd"
THUMB_ABD_FIXED_FRACTION = 0.0

LOG_DIR = Path.home() / "logs" / "hand_logs"

JOINT_ORDER: list[str] = [joint for joints in FINGER_JOINTS.values() for joint in joints] + [THUMB_ABD_JOINT]


def load_calibration(path: Path) -> dict[str, dict[str, float]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"No calibration file at {path}.\n"
            "Run calibration first (with senseglove_bridge.py running):\n"
            "  uv run python -m orca_motionTracker.Input.calibrate_hand"
        )
    with open(path) as f:
        data = json.load(f)

    print(f"Loaded calibration from {path} (saved {data.get('timestamp', 'unknown time')}):")
    for name in FINGERS:
        entry = data["fingers"][name]
        print(f"  {name:>7}: open={entry['open']:.4f} closed={entry['closed']:.4f}")

    return data["fingers"]


def apply_calibration(raw_flexion: dict[str, float], calibration: dict[str, dict[str, float]]) -> dict[str, float]:
    fractions: dict[str, float] = {}
    for name in FINGERS:
        entry = calibration[name]
        raw = raw_flexion[name]
        fraction = raw * entry["scale"] + entry["offset"]
        fractions[name] = float(np.clip(fraction, 0.0, 1.0))
    return fractions


def fractions_to_finger_positions(hand, fractions: dict[str, float]) -> OrcaJointPositions:

    pose_dict: dict[str, float] = {}
    for joint, fraction in fractions.items():
        joint_min, joint_max = hand.config.joint_roms_dict[joint]
        open_value = (
            hand.config.neutral_position[joint]
            if joint in OPEN_AT_NEUTRAL_JOINTS
            else joint_min
        )
        pose_dict[joint] = open_value + float(fraction) * (joint_max - open_value)
    return hand.config.clamp_joint_positions(OrcaJointPositions.from_dict(pose_dict))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drive the physical OrcaHand directly from a SenseGlove over UDP, no orca_teleop."
    )
    add_hand_arguments(parser)
    parser.add_argument(
        "--calibration",
        type=Path,
        default=CALIBRATION_FILE,
        help="hand_calibration.json produced by Input/calibrate_hand.py",
    )
    parser.add_argument("--host", default="0.0.0.0", help="UDP listen host")
    parser.add_argument(
        "--port", type=int, default=5010, help="UDP listen port (must match senseglove_bridge.py's --port)"
    )
    parser.add_argument("--rate-hz", type=float, default=60.0, help="Control loop rate")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.25,
        help="Seconds of silence before a flexion reading is treated as stale/missing",
    )
    parser.add_argument(
        "--num-steps",
        type=int,
        default=1,
        help="Interpolation steps per command (1 = immediate, for lowest latency)",
    )
    args = parser.parse_args()

    calibration = load_calibration(args.calibration)

    hand = create_hand_from_args(args)
    receiver = FlexionUDPReceiver(host=args.host, port=args.port, timeout=args.timeout)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    csv_path = LOG_DIR / f"hand_teleop_{timestamp_str}.csv"
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.DictWriter(
        csv_file,
        fieldnames=(
            ["timestamp", "sequence"]
            + [f"raw_{name}" for name in FINGERS]
            + [f"scaled_{name}" for name in FINGERS]
            + [f"cmd_{joint}" for joint in JOINT_ORDER]
            + [f"actual_{joint}" for joint in JOINT_ORDER]
        ),
    )

    csv_writer.writeheader()
    print(f"Logging to {csv_path}")
    last_flush_time = time.monotonic()

    try:
        connect_hand(hand)
        hand.init_joints()
        print("Moving to neutral position...")
        hand.set_neutral_position()

        period = 1.0 / args.rate_hz
        print("\nStreaming. Press CTRL+C to stop. (Make sure senseglove_bridge.py is running.)\n")

        while True:
            loop_start = time.monotonic()

            raw_flexion = receiver.get_latest()
            if raw_flexion is None:

                elapsed = time.monotonic() - loop_start

                if elapsed < period:
                    time.sleep(period - elapsed)
                continue

            fractions = apply_calibration(raw_flexion, calibration)
            joint_fractions: dict[str, float] = {}
            for name, fraction in fractions.items():
                for joint in FINGER_JOINTS[name]:
                    joint_fractions[joint] = fraction

            joint_fractions[THUMB_ABD_JOINT] = THUMB_ABD_FIXED_FRACTION

            pose = fractions_to_finger_positions(hand, joint_fractions)

            pose_dict = pose.as_dict()

            hand.set_joint_positions(pose, num_steps=args.num_steps)

            actual_pose = hand.get_joint_position().as_dict()

            row = {
                "timestamp": time.time(),
                "sequence": receiver.get_latest_sequence(),
            }
            for name in FINGERS:
                row[f"raw_{name}"] = raw_flexion[name]
                row[f"scaled_{name}"] = fractions[name]
            for joint in JOINT_ORDER:
                row[f"cmd_{joint}"] = pose_dict.get(joint)
                row[f"actual_{joint}"] = actual_pose.get(joint)
            
            csv_writer.writerow(row)

            if time.monotonic() - last_flush_time >= 1.0:
                csv_file.flush()
                last_flush_time = time.monotonic()

            elapsed = time.monotonic() - loop_start
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        receiver.close()
        if not csv_file.closed:
            csv_file.flush()
            csv_file.close()
        try:
            print("Returning to neutral...")
            hand.set_neutral_position()
        except Exception:
            pass
        shutdown_hand(hand)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
