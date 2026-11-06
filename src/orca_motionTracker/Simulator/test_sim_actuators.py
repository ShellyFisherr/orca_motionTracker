import time
import numpy as np
import mujoco

from orca_sim import OrcaHandRight

def main():

    env = OrcaHandRight(render_mode="human")

    try:

        env.reset()

        action_size = env.action_space.shape[0]

        print("\nActuator control ranges: ")
        print(env.model.actuator_ctrlrange)

        print("\nStarting Actuator Tests...")

        for i in range(action_size):

            env.reset()

            action = np.zeros(action_size, dtype=np.float32)

            name = mujoco.mj_id2name(
                env.model,
                mujoco.mjtObj.mjOBJ_ACTUATOR,
                i
            )

            lower = env.action_space.low[i]
            upper = env.action_space.high[i]


            value_1 = lower + 0.30 * (upper - lower)
            value_2 = lower + 0.70 * (upper - lower)

            print(f"\nTesting actuator {i}: {name}")
            print(f"  Range: [{lower:.3f}, {upper:.3f}]")
            print(f" First command: {value_1:.3f}")
            print(f" Second command: {value_2:.3f}")

            action[i] = value_1

            for _ in range(45):
                env.step(action)
                time.sleep(1 / 30)

            action[i] = value_2

            for _ in range(45):
                env.step(action)
                time.sleep(1 / 30)

            input("\nPress Enter to continue to the next actuator...")

        print("\nActuator tests completed.")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")

    finally:
        env.close()

if __name__ == "__main__":
    main()