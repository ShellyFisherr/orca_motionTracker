import json
import time
import numpy as np
import mujoco

from pathlib import Path
from datetime import datetime
from statistics import median

from orca_sim import OrcaHandRight

from orca_motionTracker.Processing.finger_mapping import (FINGER_ACTUATORS, FINGERS)

from orca_motionTracker.Processing.flexion_to_action import flexion_to_action

SETTLE_TIME = 2.0
SAMPLE_COUNT = 30
SAMPLERATE = 60.0

MIN_JOINT_RANGE = 0.05

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_FILE = PROJECT_ROOT / "config" / "simulation_calibration.json"


def get_finger_joints(env):

    model = env.model

    finger_joints = {}

    for finger, actuator_indices in FINGER_ACTUATORS.items():

        finger_joints[finger] = []

        for actuator_id in actuator_indices:
            if actuator_id >= model.nu:
                raise ValueError(f"Actuator index {actuator_id} does not exits")

            if(model.actuator_trntype[actuator_id] != mujoco.mjtTrn.mjTRN_JOINT):
                raise ValueError(f"Actuator {actuator_id} is not connected directly to a joint")

            joint_id = int(model.actuator_trnid[actuator_id, 0])

            joint_name = mujoco.mj_id2name(
                model,
                mujoco.mjtObj.mjOBJ_JOINT,
                joint_id
            )

            if joint_name is None:
                joint_name = f"joint_{joint_id}"

            joint_type = int(env.model.jnt_type[joint_id]
)
            if joint_type not in (
                int(mujoco.mjtJoint.mjJNT_HINGE),
                int(mujoco.mjtJoint.mjJNT_SLIDE)):
                raise ValueError(f"{joint_name} is not a scalar joint")

            finger_joints[finger].append({
                "joint_id": joint_id,
                "joint_name": joint_name,
                "qpos_address": int(model.jnt_qposadr[joint_id])
            })
    return finger_joints


def collect_pose(env, action, finger_joints, pose_name):

    sample_interval = 1 / SAMPLERATE

    print(f"\nSetting hand to {pose_name} position...")

    settle_steps = int(SETTLE_TIME * SAMPLERATE)

    for _ in range(settle_steps):
        env.step(action)
        time.sleep(sample_interval)

    print(f"Collecting {SAMPLE_COUNT} joint measurements...")

    samples = {
        finger: {
            joint["joint_name"]: []
            for joint in joints
        }
        for finger, joints in finger_joints.items()
    }

    for sample_index in range(SAMPLE_COUNT):

        env.step(action)

        for finger, joints in finger_joints.items():

            for joint in joints:
                position = float(env.data.qpos[joint["qpos_address"]])

                samples[finger][joint["joint_name"]].append(position)

        print(f"\rSamples: {sample_index+1}/{SAMPLE_COUNT}",
              end="",
              flush=True)
        
        time.sleep(sample_interval)

    print("\nCollection complete.")

    references = {}

    for finger, joints in samples.items():

        references[finger] = {}

        for joint_name, measurements in joints.items():

            references[finger][joint_name] = median(measurements)

    return references


def validate_calibration(open_reference, closed_reference):

    valid = True

    print("\nChecking simulation calibration:")
    for finger in FINGERS:

        print(f"\n{finger.upper()}:")
        
        for joint_name in open_reference[finger]:

            open_value = open_reference[finger][joint_name]
            closed_value = closed_reference[finger][joint_name]

            difference = closed_value - open_value

            print(
                f"  {joint_name}:"
                f"open={open_value:.4f}, "
                f"closed={closed_value:.4f}, "
                f"range={difference:.4f}"
            )

            if abs(difference) < MIN_JOINT_RANGE:
                print(f"WARNING: Insufficient movement for {joint_name}.")

                valid = False

    return valid

def save_calibration(open_reference, closed_reference):

    calibration = {
        "calibration_version": 1,

        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),

        "sample_count": SAMPLE_COUNT,

        "method": "medain",

        "fingers": {}
    }

    for finger in FINGERS:

        calibration["fingers"][finger] = {}

        for joint_name in open_reference[finger]:

            calibration["fingers"][finger][joint_name] = {
                "open": open_reference[finger][joint_name],
                "closed": closed_reference[finger][joint_name],
                "difference": closed_reference[finger][joint_name] - open_reference[finger][joint_name]
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

    print("\nSimulation calibration successfully saved.")
    print(f"Location: {CALIBRATION_FILE}")


def main():

    env = OrcaHandRight(render_mode="human")

    try:
        env.reset()

        action_low = env.action_space.low
        action_high = env.action_space.high

        finger_joints = get_finger_joints(env)

        print("\n====================================")
        print("       SIMULATION CALIBRATION")
        print("====================================")

        print("\nDetected Finger joints:")

        for finger, joints in finger_joints.items():

            print(f"{finger.upper()}:")

            for joint in joints:
                print(f"  {joint['joint_name']}")

        input("\nMake sure hand simulation in loaded and ready.\n"\
              "Press ENTER to start the calibration...")

        open_flexion = {
            finger: 0.0
            for finger in FINGERS
        }

        open_action = flexion_to_action(
            open_flexion,
            action_low,
            action_high
        )

        open_reference = collect_pose(
            env,
            open_action,
            finger_joints,
            "OPEN"
        )

        input("\nPress ENTER to continue next calibration step...")

        closed_flexion = {
            finger: 1.0
            for finger in FINGERS
        }

        closed_action = flexion_to_action(
            closed_flexion,
            action_low,
            action_high
        )

        closed_reference = collect_pose(
            env,
            closed_action,
            finger_joints,
            "CLOSED"
        )


        print("\n=================================")
        print("       CALIBRATION RESULTS")
        print("=================================")

        valid = validate_calibration(open_reference, closed_reference)

        if not valid:
            "\nCalibration rejected. At least one joint did not move sufficiently."
            return

        save_calibration(open_reference, closed_reference)

    except KeyboardInterrupt:
        print("\nCalibration interupted by user.")

    finally:
        env.close()
        print("\nSimulation closed")

if __name__ == "__main__":
    main()



