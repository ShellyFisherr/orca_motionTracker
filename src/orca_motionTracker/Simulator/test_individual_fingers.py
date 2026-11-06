import time

from orca_sim import OrcaHandRight
from orca_motionTracker.Processing.flexion_to_action import flexion_to_action

def hold_action(env, action, duration=2.0):

    steps = int(duration * 30)

    for _ in range(steps):
        env.step(action)
        time.sleep(1 / 30)


def main():
    env = OrcaHandRight(render_mode="human")

    fingers = ["thumb", "index", "middle", "ring", "pinky"]

    try:
        env.reset()

        low = env.action_space.low
        high = env.action_space.high

        for finger in fingers:
            env.reset()

            flexion = {
                "thumb": 0.0,
                "index": 0.0,
                "middle": 0.0,
                "ring": 0.0,
                "pinky": 0.0
            }

            print(f"\nTesting {finger} finger flexion...")

            flexion[finger] = 1.0

            action = flexion_to_action(flexion, low, high)

            hold_action(env, action)

            flexion[finger] = 0.0

            action = flexion_to_action(flexion, low, high)

            hold_action(env, action)

    finally:
        env.close()

if __name__ == "__main__":
    main()
            