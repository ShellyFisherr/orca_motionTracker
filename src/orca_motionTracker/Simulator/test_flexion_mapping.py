import time
import numpy as np

from orca_sim import OrcaHandRight

from orca_motionTracker.Processing.flexion_to_action import flexion_to_action


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

        test_values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2]

        for value in test_values:
            env.reset()

            flexion = {
                "thumb": value,
                "index": value,
                "middle": value,
                "ring": value,
                "pinky": value
            }

            action = flexion_to_action(flexion, low, high)

            print(f"\nTesting flexion value: {value:.2f}"
                  f"\nAction values: {action}")

            hold_action(env, action)

            input("Press Enter to continue to the next flexion value...")

    except KeyboardInterrupt:
        print("\nUser interrupted the test. Exiting...")

    finally:
        env.close()

if __name__ == "__main__":
    main()

        