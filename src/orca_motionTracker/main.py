import time

import numpy as np
from orca_sim import OrcaHandRight


def main() -> int:
    env = OrcaHandRight(render_mode="human")
    try:
        observation, info = env.reset()
        print(f"Observation shape: {observation.shape}")

        target = np.zeros(env.action_space.shape, dtype=np.float32)

        for index in (2, 3, 5, 6, 8, 9, 11, 12):
            target[index] = 0.2

        for _ in range(1000):
            observation, reward, terminated, truncated, info = env.step(target)
            time.sleep(1 / 30)

            if terminated or truncated:
                observation, info = env.reset()
        return 0
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())