import mujoco
from orca_sim import OrcaHandRight


def main():

    # Start the simulated right hand
    env = OrcaHandRight(render_mode="human")

    try:
        observation, info = env.reset()

        print("\nORCA HAND SIMULATION")
        print("====================")

        print(f"Observation shape: {observation.shape}")
        print(f"Action shape: {env.action_space.shape}")
        print(f"Number of actuators: {env.model.nu}")

        print("\nACTUATOR INFORMATION")
        print("====================")

        for i in range(env.model.nu):

            name = mujoco.mj_id2name(
                env.model,
                mujoco.mjtObj.mjOBJ_ACTUATOR,
                i
            )

            lower = env.action_space.low[i]
            upper = env.action_space.high[i]

            print(
                f"Index {i:2d}: "
                f"{name:25s} "
                f"Min: {lower:8.3f} "
                f"Max: {upper:8.3f}"
            )

        input("\nPress Enter to close the simulation...")

    finally:
        env.close()


if __name__ == "__main__":
    main()