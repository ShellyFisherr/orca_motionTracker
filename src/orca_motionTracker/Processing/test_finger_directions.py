import time
import numpy as np

from orca_sim import OrcaHandRight
from orca_motionTracker.Processing.finger_mapping import FINGER_ACTUATORS


def hold_action(env, action, duration=2.0):

    steps = int(duration * 30)

    for _ in range(steps):
        env.step(action)
        time.sleep(1 / 30)


def main():

    env = OrcaHandRight(render_mode="human")

    try:
        env.reset()

        low = env.action_space.low
        high = env.action_space.high

        action = np.zeros(env.action_space.shape, dtype=np.float32)


        for finger, indices in FINGER_ACTUATORS.items():

            env.reset()

            action[:] = 0.0

            print(f"\nTesting {finger} finger actuators: {indices}")

            for i in indices:
                action[i] = low[i] + 0.15 * (high[i] - low[i])

            print(" Observe the finger moving to the first position...")

            hold_action(env, action)

            input("Press Enter to continue to the next position...")

            for i in indices:
                action[i] = low[i] + 0.8 * (high[i] - low[i])

            print(" Observe the finger moving to the second position...")

            hold_action(env, action)

            input("Press Enter to continue to the initial position...")

            for i in indices:
                action[i] = low[i] + 0.15 * (high[i] - low[i])

            print(" Observe the finger moving back to the first position...")
            hold_action(env, action)

            input("Press Enter to continue to the next finger...")

        print("\nFinger actuator tests completed.")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")

    finally:
        env.close()

if __name__ == "__main__":
    main()
