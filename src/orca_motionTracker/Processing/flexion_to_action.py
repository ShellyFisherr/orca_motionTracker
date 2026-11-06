import numpy as np

from orca_motionTracker.Processing.finger_mapping import FINGER_ACTUATORS

OPEN_FRACTION = 0.2
CLOSED_FRACTION = 1.0

THUMB_FIXED_ACTUATOR = 2
THUMB_FIXED_FRACTION = 0.15


def flexion_to_action(flexion, action_low, action_high):

    action = np.zeros(len(action_low), dtype=np.float32)

    for finger in flexion:
        flexion[finger] = np.clip(flexion[finger], 0.0, 1.0)

    for finger, indices in FINGER_ACTUATORS.items():

        finger_flexion = flexion[finger]

        fraction = (
            OPEN_FRACTION
            + finger_flexion * (CLOSED_FRACTION - OPEN_FRACTION)
        )

        for i in indices:

            # Start with the normal flexion fraction
            actuator_fraction = fraction

            # Keep thumb actuator 2 fixed
            if finger == "thumb" and i == THUMB_FIXED_ACTUATOR:
                actuator_fraction = THUMB_FIXED_FRACTION

            action[i] = (
                action_low[i]
                + actuator_fraction * (action_high[i] - action_low[i])
            )

    return action