# CODE_DETAILS for the main pipeline

## 1. Input/udp_receiver.py

A non-blocking UDP socket wrapper. One instance is created per process (`calibrate_hand.py` creates one, `hardware_teleop.py` creates another) and ech just binds to host:port and polls.

```text
Packet format (ASCII, comma-separated):
    "sequence,thumb,index,middle,ring,pinky"
```
- sequence: monotonically increasing integer, depicts the packet number send
- Flexion values: floats, expected in [0.0, 1.0]

`get_latest()` is the only method callers actually use per loop tick.
Each call does:
1. Drain the socket completely (loops recvfrom() until BlockingIOError, i.e. "no more mpackets waiting right now") so it always processes every packet that arrived since the last call, not just one.
2. For each packet: splits the data on comma, validates it has exactly 6 transmitted values, values every flexion received is finite [0.0, 1.0], tracks sequency number to detect if any packets received were out of order or missing or duplicated. (only for stats counters, data types are not rejected sincec it is not neccesarily needed).
3. Keeps onl the single newest valid packet as self.latest_flexion.
4. After draining all data, checks for staleness. If this is longer than the pre-set `timeout` since the last valid packet arrived, it returns a `None` value instead of a stale reading. Otherwise returns a dict {"thumb": ..., "index":. ..., ...}

It is set in a "latest value wins" design instead of a queue to prevent any latency from adding up in teh system.

Note: get_statistics() exists, which counts the invalid sequences received, but nothing in the active pipeline reads it. -- its purely for debugging.

---

## 2. Processing/finger_mapping.py

Just data, no logic.

```python
FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
```
`FINGER_ACTUATORS` / `FINGER_JOINTS` = per-finger actuator / joint name lists, used by the Simulator/scripts (MuJoCo actuator indices) and some Processing helpers. NOT used by hardware_teleop.py, which defines its own FINGER_JOINTS dict locally instead (the real orca_core joint names like "index_mcp", not the MuJoCo/sim names like "right_index_mcp" this file has).

Its worth noting that `hardware_teleop.py` creates its own dict instead of using the one from `finger_mapping.py` since it uses different naming conventions.

---

## 3. Input/calibrate_hand.py

Run manually before running `hardware_teleop.py` will work at all.

Prompts the user via the terminal to say what to do. It waits for an `ENTER` input before reading data, and then waits for 120 fresh UDP packet samples. counts genuinely new readings, same latest-value-wins pattern as the receiver in `hardware_teleop.py` itself. Takes per finger median as the final reference to minimize tracker noise.

```python
validate_calibration()

then per finger:
difference = closed_value - open_value
scale = 1.0 / difference
offset = -open_value * scale
```

This is just solving for the linear mapping between glove and hand.
$f_{raw} = raw * scale + offset$ such that $f_{\text{open value}} = 0$ and $f_{\text{closed value}} = 1$, Thus turning whatever raw range is received into a clean [0.0, 1.0] scaled flexion. If the difference is less than a base parameterized value ($scale < 0.10$). for any finger, the entire calibration is rejected. (The glove is most likely too loose, resulting in an untrustworthy scale). It saves the final data to `hand_calibration.json` in the `config` file. `hardware_teleop.py` then reads this data and uses it to scale the incoming parameter packets to the corresponding robot parameters. 

---

### 4. Control/hardware_teleop.py

load_calibration(path): reads `hand_calibration.json`, prints the summary and returns the `fingers` dict.

apply_calibration(raw_flexion, calibration): re-applies the exact same scale / offset formula from `calibrate_hand.py` to turn the glove-frame values into clipped [0.0, 1.0] robot-frame values. One per finger.

```python
FINGER_JOINTS (local to this file, real orca_core joint names):
    thumb:  thumb_mcp, thumb_dip
    index:  index_mcp, index_pip
    middle: middle_mcp, middle_pip
    ring:   ring_mcp, ring_pip
    pinky:  pinky_mcp, pinky_pip
```

Each finger's single flexion fraction gets broadcast to both of its listed joints identically, there's no independent per-joint control, the glove only gives one curl value per finger. `thumb_cmc` and all five abduction joints are deliberately absent from this dict, so they're never touched by this fan-out and stay wherever `hand.init_joints()`/`set_neutral_position()` left them, except for thumb_abd which gets special-cased below.

``` python
fractions_to_finger_positions(hand, fractions) -- the actual mapping
from a [0,1] fraction to a real joint angle:
    joint_min, joint_max = hand.config.joint_roms_dict[joint]
    open_value = neutral_position[joint]   if joint in OPEN_AT_NEUTRAL_JOINTS
                 else joint_min
    angle = open_value + fraction * (joint_max - open_value)
```

So it's a linear interpolation, but the "0" end isn't always the raw
ROM minimum:
- For `thumb_mcp`/`thumb_dip`: 0 -> ROM min, 1 -> ROM max (unchanged, looked correct as-is).
- For the other 8 joints (index/middle/ring/pinky mcp+pip, listed in `OPEN_AT_NEUTRAL_JOINTS`): 0 -> that joint's configured `neutral_position` instead of ROM min, 1 -> ROM max unchanged. This is the fix for "fingers too far back when fully open", the raw ROM minimum over-extended past a natural resting pose, so "fully open" now lands on the hand's own defined neutral instead.

Then `clamp_joint_positions()` (orca_core's own safety clamp) is applied
before returning.

Deliberately narrow: it only builds angles for joints present in the `fractions` dict passed in -- never touches wrist/thumb_cmc/abduction via this path, both because nothing drives them from glove data and because querying/commanding a joint whose motor doesn't answer cleanly can add retry delay to every single frame.

main() -- the run loop:
  1. argparse: --calibration, --host/--port (UDP), --rate-hz, --timeout, --num-steps, plus whatever add_hand_arguments() contributes from orca_core (bus connection options).
  2. Load calibration, connect to the real hand, init joints, move to neutral_position once at startup.
  3. Loop at --rate-hz:

```python
raw_flexion = receiver.get_latest
if None: "hold the last pose, skip this iteration (don`t guess a replacement value, don't re-send the same command either)"
else: fractions = apply_calibration(raw_flexion, calibration)
    joint_fractions = "fan out each finger's fraction to its two joints via FINGER_JOINTS"
    joint_fractions[thumb_abd] = THUMB_ABD_FIXED_FRACTION (0.0)
t"humb_abd isn't driven by any finger's curl at all; it's pinned every frame at fraction 0, which (per fractions_to_finger_positions, thumb_abd isn't in OPEN_AT_NEUTRAL_JOINTS) resolves to thumb_abd's ROM minimum, the opposite end from its configured neutral, which is the side it's meant to rest on."
pose = fractions_to_finger_positions(hand, joint_fractions)
hand.set_joint_positions(pose, num_steps=args.num_steps)
```
$\space\space\space\space\space\space\space\space$ Sleep out whatever's left of the frame period (busy-loop style
timing, not a hardware timer).

  4. On Ctrl+C or exit: return to neutral_position, then `shutdown_hand()`. r`eceiver.close()` always runs via finally.

There is no filtering in and of itself since the sensors from the hand are already quite accurate, and no direct motion is detected on standstill.

No controller is present in the `orca_motionTracker` package since the `orca_core` package already has a build in PID controller into each motor to correct the errors, and `orca_core` itself also has a PI controller build in. adding more controllers would most likely result in unnecairy complication and added noise. As with testing with this control scheme, no direct drift correlated to the control scheme itself was observed.