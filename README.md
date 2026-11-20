# orca_motionTracker - SenseGlove $\rightarrow$ OrcaHand teleop

This project is an extension from the main [orcaHand project](https://github.com/orcahand) by [ORCA dexterity](https://www.orcahand.com)

It drives a physical ORCA hand directly from a [SenseGlove Nova 2 teleop](https://github.com/ShellyFisherr/senseglove_teleop) using scalar per-finger flexion value streamed over a UDP network.

## Layout:

- [**1. Pipeline**](#pipeline)
- [**2. Prerequisutes**](#prerequisites)
- [**3. Install Guide**](#install-guide)
- [**4. How to Run**](#how-to-run)
- [**5. Parameters**](#parameters)
- [**6. Code Explaination**](#code-explaination)
- [**7. Troubleshooting**](#troubleshooting)

## Pipeline

Pipeline:
```text
senseglove_teleop (C++, --udp mode)
    -> UDP bridge
    -> Input/udp_receiver.py
    -> Input/Calibrate_hand.py (one time calibration between runs)
    -> Control/hardware_teleop.py (load calibration parameters and commands the physical hand)
```

## Prerequisites
- Linux, Python >= 3.11
- uv (for dependence management; this project uses a uv-managed venv, copied from orca-project)
- orca_core and orca_sim from ORCA dexterity installed (guide link provided in the install guide)
- the SenseGlove C++ reader. (guide link provided in install guide)
- orcaHand v2 base right hand (could potentially be compatible with other orcahand versions, but this is not tested and should be done at your own risk, so take caution with that.)

## Install Guide

If you do not yet have the `SenseGlove C++ reader` package, follow the [Install Guide](https://github.com/ShellyFisherr/senseglove_teleop) and return here afterwards.

create a new file to put all the code in using
```bash
cd ~
mkdir -p ~/RobotHand/orcahand
```
from here follow the install guide for [orca_core](https://github.com/orcahand/orca_core). Note: [orca_sim](https://github.com/orcahand/orca_sim) and [orcahand_description](https://github.com/orcahand/orcahand_description) can optionally be installed to run the simulated version, but is not needed and not covered in the main physical hand pipeline 

Afterwards, your file setup should look like:
```text
└── RobotHand
    ├── ...
    ├── senseglove
    └── orcahand
        ├── orca_core
        ├── orcahand_description (optional)
        └── orca_sim (optional)
```

now to clone this actual package use
```bash
sudo apt update

cd  ~/RobotHand/orcahand
git clone https://github.com/ShellyFisherr/orca_motionTracker
```
resulting in the file structure:
```text
└── RobotHand
    ├── ...
    ├── senseglove
    └── orcahand
        ├── orca_core
        ├── orca_motionTracker
        ├── orcahand_description (optional)
        └── orca_sim (optional)
```

now install and sync the root using
```bash
cd ~/RobotHand/orcahand/orca_motionTracker
uv sync
```

no .env or config file is required for the install, as these are generated later upon calibration. This simply installs all packages in editable mode
s
## How to Run

All commands run from the `orca_motiontTracker` root (except the `senseglove_reader`), with `uv run`. The root is accessed using
```bash
cd ~/RobotHand/orcahand/motionTracker
```

To start, run the senseglove reader to start the UDP package sender
```bash
cd ~/RobotHand/senseglove/senseglove_teleop
./build/senseglove_teleop --udp
```
Leave this running in its own terminal. It talks to SenseCom and streams one UDP packer per frame.


Next up, calibrate the system. (only needs to be redone when you want to. It is adviced to redo the calibration when redoing the SenseCom calibration, and when switching between users)

```bash
uv run python -m orca_motionTracker.Input.calibrate_hand
```

Follow the prompts that appear until the calibration has completed successfully. If any finger is rejected since the open and closed positions are too close together, refit that finger and restart the calibration process. It is adviced when refitting or readjusting the fingers on the glove, to also redo the calibration in the SenseCom program.


From here, you can run the real hand. This program was tested only on the orca_hand v2 right hand without tactile sensing. Different versions of the hand could work depending on the software compatibilities of set hand, but it cannot be guaranteed and is not tested, so caution is adviced. Make sure in that case to also use the correct `config.yaml` file from `orca_core`

The real hand is run using
```bash
uv run python -m orca_motionTracker.Control.hardware_teleop \
    ../orca_core/orca_core/models/v2/orcahand-right/config.yaml
```

The hand will move to its natural position first, after which it will start following the glove positions. Upon exiting the program, it returns to its natural position.

## Parameters

Nothing is hardcoded that needs manual editting, nor are there any config files from `orca_motionTracker` that should be adjusted manually. The only file you may ever edit is the corresponding hand `config.yaml` from `orca_core` itself.

`hardware_teleop.py` does have some command-line flags, all with set defaults:

- `--calibration PATH`: path to hand_calibration.json. (default: config/hand_calibration.json)
- `--host HOST`: UDP listen host (default: 0.0.0.0)
- `--port PORT`: UDP listen port (default: 5010 - must match the senseglove_teleop port)
- `--rate-hz HZ`: The control frequency of the system (default: 60, since senseglove standard does not read faster than this, it is not adviced to edit it)

- `--num-steps N`: Interpolation steps per commanded pose. (default: 1 = send instantly, lowest latency).

`calibrate_hand.py` takes no arguments, it only writes the calibration path and always listens to port 0.0.0.0:5010

## code explaination

A code explaination regarding the main pipeline can be found in [CODE_DETAILS](CODE_DETAILS.md)

## Troubleshooting

No UDP data arriving / `calibrate_hand.py` hangs at "Waiting for SenseGlove data...":
  - Confirm senseglove_teleop --udp is actually running and hasn't exited/errored.
  - Confirm it's sending to the same port `hardware_teleop.py` / `calibrate_hand.py` are listening on (default 5010 both sides).
  - Check nothing else is bound to that port already (`ss -ulnp | grep 5010`).

Calibration keeps failing with "insufficient calibration range":
  - Usually a loose/slipped glove fit on that specific finger, not a software bug. Refit and redo that finger's open/closed pose.
  - Could also mean the glove itself is drifted — recalibrate the glove in SenseCom first, then redo this calibration.

Finger drifts out of its calibrated range after a while, even though
nothing in config changed:
  - This has previously turned out to be SenseGlove Nova 2 IMU tracking drift, not an OrcaHand/motor issue. Fix: recalibrate the glove itself via SenseCom's GUI, then redo Input/calibrate_hand.py.

`hardware_teleop.py` exits immediately with "No calibration file at ...":
  - Run Input/calibrate_hand.py first; it must be done at least once before `hardware_teleop.py` can start.

Hand looks right on open/close but thumb or finger positions look physically wrong (overshoot / hyperextension, thumb swung the wrong way):
  - This is the OPEN_AT_NEUTRAL_JOINTS / THUMB_ABD_FIXED_FRACTION logic in `hardware_teleop.py`
  - intentional, not a bug, but if it ever needs tuning per-hand, those are the two constants to look at.

Everything connects but motion feels laggy/stuttery:
  - Try --num-steps 1 (lowest latency, default) if it was raised.
  - Check --rate-hz matches realistically what the glove side can sustain; mismatched rates won't crash anything but can feel uneven.

<!-- ├── -->
<!-- └──  -->