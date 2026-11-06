import numpy as np
import mujoco
from orca_motionTracker.Processing.finger_mapping import FINGER_JOINTS

def read_finger_bending(env, joint_references):

    bending = {}

    model = env.model
    data = env.data

    for finger, joints in FINGER_JOINTS.items():

        joint_bending = []

        for joint_name in joints:

            joint_id = mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_JOINT,
                joint_name
            )

            if joint_id < 0:
                raise ValueError(f"Joint not found: {joint_name}")

            joint_type = int(model.jnt_type[joint_id])

            if joint_type not in (
                int(mujoco.mjtJoint.mjJNT_HINGE),
                int(mujoco.mjtJoint.mjJNT_SLIDE)):
                raise ValueError(f"{joint_name} is not a scalar joint")

            qpos_address = int(model.jnt_qposadr[joint_id])
            actual_position = data.qpos[qpos_address]

            open_position = joint_references[finger][joint_name]["open"]
            closed_position = joint_references[finger][joint_name]["closed"]

            difference = closed_position - open_position

            if abs(difference) < 0.1:
                raise ValueError(f"Invalid joint reference for {joint_name}")

            value = (actual_position - open_position) / difference

            joint_bending.append(np.clip(value, 0.0, 1.0))

        bending[finger] = float(np.mean(joint_bending) * 100)

    return bending