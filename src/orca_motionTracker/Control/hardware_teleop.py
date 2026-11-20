"""Direct SenseGlove -> physical OrcaHand teleop, bypassing orca_teleop entirely.

Reads live per-finger flexion over UDP via the same FlexionUDPReceiver used
throughout orca_motionTracker (Input/udp_receiver.py), published by
Input/senseglove_bridge.py from the real Linux SenseGlove reader, and loads
the calibration produced by the existing Input/calibrate_hand.py
(config/hand_calibration.json: median open/closed plus linear scale/offset
per finger). Drives the real OrcaHand's flexion joints directly via
orca_core's own ROM-based fraction mapping. No gRPC, no retargeter, no
torch -- and this process never touches senseglove_reader's raw binary
stream at all; that happens exactly once, in the bridge.

Usage (three terminals):
    # 1) bridge: C++ reader -> UDP (leave running)
    uv run python -m orca_motionTracker.Input.senseglove_bridge

    # 2) calibrate -- writes config/hand_calibration.json. Run once, or
    #    again whenever you want to recalibrate.
    uv run python -m orca_motionTracker.Input.calibrate_hand

    # 3) drive the real hand
    uv run python -m orca_motionTracker.Control.hardware_teleop \\
        ../orca_core/orca_core/models/v2/orcahand-right/config.yaml
"""

from __future__ import annotations

import argparse
import json
import time
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

# Which real orca_core joints each finger's flexion drives. Abduction and
# thumb_cmc are intentionally left out, so they stay at their configured
# neutral_position values (we only ever build fractions for the joints
# named here).
FINGER_JOINTS: dict[str, list[str]] = {
    "thumb": ["thumb_mcp", "thumb_dip"],
    "index": ["index_mcp", "index_pip"],
    "middle": ["middle_mcp", "middle_pip"],
    "ring": ["ring_mcp", "ring_pip"],
    "pinky": ["pinky_mcp", "pinky_pip"],
}

# fraction 0 ("fully open") normally maps to each joint's raw ROM minimum,
# which for these joints overshoots well past the hand's natural resting
# pose and looks hyper-extended ("fingers too far back"). For these joints,
# fraction 0 instead lands on the hand's configured neutral_position; the
# closed end (fraction 1 -> ROM max) is unchanged. The thumb's mcp/dip are
# deliberately left out -- their ROM-minimum open end already looks right.
OPEN_AT_NEUTRAL_JOINTS: set[str] = {
    "index_mcp", "index_pip",
    "middle_mcp", "middle_pip",
    "ring_mcp", "ring_pip",
    "pinky_mcp", "pinky_pip",
}

# Thumb abduction (the joint that swings the thumb left/right) isn't driven
# by flexion -- it's held fixed. Its configured neutral_position sits near
# one end of its ROM; fixing it at fraction 0 instead pins it at the
# opposite end (the ROM minimum), which is the side it should rest on.
THUMB_ABD_JOINT = "thumb_abd"
THUMB_ABD_FIXED_FRACTION = 0.0


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
    """Map finger flexion fractions straight to degrees for ONLY those joints.

    Deliberately narrower than hand.pose_from_fractions(), which returns a
    full pose for every configured joint (wrist, abduction, thumb_cmc
    included) every call. Re-sending those every frame is both unnecessary
    (nothing here drives them) and, if a joint's motor doesn't answer on the
    bus (e.g. a disconnected/misbehaving wrist motor), can add a retry/timeout
    delay to every single command. This only ever touches the joints named in
    `fractions`.
    """
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
                # No fresh UDP packet within --timeout seconds -- hold the
                # last commanded pose rather than guessing.
                elapsed = time.monotonic() - loop_start
                if elapsed < period:
                    time.sleep(period - elapsed)
                continue

            fractions = apply_calibration(raw_flexion, calibration)
            joint_fractions: dict[str, float] = {}
            for name, fraction in fractions.items():
                for joint in FINGER_JOINTS[name]:
                    joint_fractions[joint] = fraction

            # Held fixed at the opposite end of its ROM from its configured
            # neutral -- not driven by any finger's flexion.
            joint_fractions[THUMB_ABD_JOINT] = THUMB_ABD_FIXED_FRACTION

            pose = fractions_to_finger_positions(hand, joint_fractions)
            hand.set_joint_positions(pose, num_steps=args.num_steps)

            elapsed = time.monotonic() - loop_start
            if elapsed < period:
                time.sleep(period - elapsed)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        receiver.close()
        try:
            print("Returning to neutral...")
            hand.set_neutral_position()
        except Exception:
            pass
        shutdown_hand(hand)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
