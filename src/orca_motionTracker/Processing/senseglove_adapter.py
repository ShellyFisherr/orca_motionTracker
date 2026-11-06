"""Convert SenseGlove finger positions to OrcaHand landmarks."""


import numpy as np

def senseglove_to_landmarks(
        positions_mm: list[np.ndarray],
        wrist_position_mm: np.ndarray,
        axis_transform: np.ndarray,
) -> np.ndarray:

    if len(positions_mm) != 5:
        raise ValueError("Expected exactly 5 finger groups")

    wrist = np.asarray(wrist_position_mm, dtype=np.float32)
    transform = np.asarray(axis_transform, dtype=np.float32)


    if wrist.shape != (3,):
        raise ValueError("Wrist position must have shape (3,)")

    if transform.shape != (3, 3):
        raise ValueError("Axis transform mist have shape (3, 3)")

    if not np.all(np.isfinite(wrist)):
        raise ValueError("Invalid wrist coordinates")

    if not np.all(np.isfinite(transform)):
        raise ValueError("Invalid axis transform")


    landmarks = [np.zeros(3, dtype=np.float32)]

    for finger_index, finger in enumerate(positions_mm):

        finger = np.asarray(finger, dtype=np.float32)

        if finger.shape != (4, 3):
            raise ValueError(
                f"finger {finger_index}: expected (4, 3), "
                f"received: {finger.shape}"
            )

        if not np.all(np.isfinite(finger)):
            raise ValueError("Invalid finger coordinates")

        relative_m = (finger - wrist) * 0.001

        canonical_m = relative_m @ transform.T

        landmarks.extend(canonical_m)

    result = np.asarray(landmarks, dtype=np.float32)

    if result.shape != (21, 3):
        raise RuntimeError(f"Incorrect landmark output shape: {result.shape}")

    return result
