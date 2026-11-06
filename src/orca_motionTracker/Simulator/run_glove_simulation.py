import time
import json
import numpy as np
import mujoco
import csv
from datetime import datetime

from pathlib import Path
from orca_sim import OrcaHandRight

from orca_motionTracker.Processing.flexion_to_action import (flexion_to_action, OPEN_FRACTION, CLOSED_FRACTION)
from orca_motionTracker.Processing.finger_mapping import (FINGERS)
from orca_motionTracker.Input.udp_receiver import FlexionUDPReceiver
from orca_motionTracker.Simulator.simulation_bending import read_finger_bending

UDP_IP = "0.0.0.0"
UDP_PORT = 5010

POS_ERROR_GAIN_P = 1.0
POS_ERROR_GAIN_D = 1.0
DERIVATIVE_CUTOFF_HZ = 5.0

CONTROL_FREQUENCY = 60.0
CONTROL_DT = 1.0 / CONTROL_FREQUENCY

PACKET_TIMEOUT = 0.5

PROJECT_ROOT = Path(__file__).resolve().parents[3]

SIMULATION_CALIBRATION_FILE = (PROJECT_ROOT / "config" / "simulation_calibration.json")
CALIBRATION_FILE = (PROJECT_ROOT / "config" / "hand_calibration.json")
LOG_DIR = (PROJECT_ROOT / "logs")

PREVIOUS_POSITION_ERROR = {}

def load_simulation_calibration():

    with open(SIMULATION_CALIBRATION_FILE, "r") as file:
        data = json.load(file)

    return data["fingers"]

def load_calibration():

    with open(CALIBRATION_FILE, "r") as file:
        data = json.load(file)

    calibration = data["fingers"]

    for finger in FINGERS:

        if finger not in calibration:
            raise ValueError(f"Missing calibration for {finger}")

        if "scale" not in calibration[finger]:
            raise ValueError(f"Missing scale for {finger}")

        if "offset" not in calibration[finger]:
            raise ValueError(f"Missing offset for {finger}")

    print("\nCalibration loaded:")

    for finger in FINGERS:
        print(
            f"{finger:>7}: "
            f"scale={calibration[finger]['scale']:.4f}, "
            f"offset={calibration[finger]['offset']:.4f}"
        )

    return calibration

def normalize_flexion(raw_flexion, calibration):

    normalized = {}

    for finger in FINGERS:

        scale = calibration[finger]["scale"]
        offset = calibration[finger]["offset"]

        value = raw_flexion[finger] * scale + offset

        normalized[finger] = float(np.clip(value, 0.0, 1.0))

    return normalized

def apply_PD_correction(desired_flexion, previous_sim_bending, previous_actual, filtered_derivative, Kp, Kd, dt, derivative_cutoff_hz):
    # f = f_in + Kpe + kd(de)/(dt)
    corrected_flexion = {}
    p_correction = {}
    d_correction = {}
    new_filtered_derivative = {}

    if dt <=0:
        raise ValueError("Controller dt must be positive.")

    alpha = np.exp(-2.0 * np.pi * derivative_cutoff_hz * dt)

    for finger in FINGERS:

        desired = desired_flexion[finger]
        actual = previous_sim_bending[finger] / 100

        error = desired - actual
        p_term = Kp * error

        raw_derivative = (actual - previous_actual[finger]) / dt

        derivative = alpha * filtered_derivative[finger] + (1 - alpha) * raw_derivative

        d_term = Kd * derivative

        corrected = desired_flexion[finger] + p_term + d_term

        corrected_flexion[finger] = float(np.clip(corrected, 0.0, 1.0))

        p_correction[finger] = p_term
        d_correction[finger] = d_term
        new_filtered_derivative[finger] = derivative

    return (corrected_flexion, p_correction, d_correction, new_filtered_derivative)

def apply_P_correction(desired_flexion, previous_sim_bending, Kp):

    corrected_flexion = {}

    for finger in FINGERS:
        
        desired = desired_flexion[finger]
        actual = previous_sim_bending[finger] / 100.0

        position_error = desired - actual

        corrected = desired + Kp * position_error

        corrected_flexion[finger] = float(np.clip(corrected, 0.0, 1.0))

    return corrected_flexion

def main():
    print("\nLoading hand calibration...")

    calibration = load_calibration()
    simulation_calibration = load_simulation_calibration()

    receiver = FlexionUDPReceiver(
        host=UDP_IP,
        port=UDP_PORT,
        timeout=0.25
    )

    print("\nStarting OrcaHand simulation...")

    env = OrcaHandRight(render_mode="human")

    try:
        env.reset()

        previous_sim_bending = read_finger_bending(env, simulation_calibration)

        previous_actual = {finger: previous_sim_bending[finger] / 100 for finger in FINGERS}

        filtered_derivative = {finger: 0.0 for finger in FINGERS}

        action_low = env.action_space.low
        action_high = env.action_space.high

        flexion = {
            finger: 0.0
            for finger in FINGERS
        }

        action = flexion_to_action(
            flexion,
            action_low,
            action_high)

        print("\nSimulation running.")
        print("Waiting for SenseGlove data...")

        LOG_DIR.mkdir(
            parents=True,
            exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = (LOG_DIR / f"hand_sim_teleop_{timestamp}.csv")

        csv_file = open(csv_path, "w", newline="")
        csv_writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                ["time_s", "sequence", "glove_data_fresh"]
                + [f"{finger}_raw" for finger in FINGERS]
                + [f"{finger}_input_pct" for finger in FINGERS]
                + [f"{finger}_corrected_pct" for finger in FINGERS]
                + [f"{finger}_simulated_pct" for finger in FINGERS]

                + ["control_frequency_hz",
                   "control_dt_s",
                   "packet_timeout_s",
                   "position_error_gain_P",
                   "position_error_gain_D",
                   "open_fraction",
                   "closed_fraction"
                   ]
            )
        )

        csv_writer.writeheader()

        print(f"\nlogging data to: {csv_path}")

        start_time = time.monotonic()
        prev_time = start_time
        last_flush_time = start_time

        while True:

            loop_start = time.monotonic()

            dt = loop_start - prev_time
            prev_time = loop_start
            
            raw_flexion = receiver.get_latest()

            if raw_flexion is not None:
                flexion = normalize_flexion(raw_flexion, calibration)

            if raw_flexion is None:
                pass

            sequence = receiver.get_latest_sequence()

            corrected_flexion, p_correction, d_correction, filtered_derivative = apply_PD_correction(
                flexion,
                previous_sim_bending,
                previous_actual,
                filtered_derivative,
                POS_ERROR_GAIN_P,
                POS_ERROR_GAIN_D,
                dt,
                DERIVATIVE_CUTOFF_HZ)

            # corrected_flexion = apply_P_correction(flexion, previous_sim_bending, POS_ERROR_GAIN_P)

            action = flexion_to_action(
                corrected_flexion,
                action_low,
                action_high
            )

            result = env.step(action)
            simulated_bending = read_finger_bending(env, simulation_calibration)

            previous_sim_bending = simulated_bending

            previous_actual = {
                finger: simulated_bending[finger] / 100.0
                for finger in FINGERS
            }
            
            if len(result) == 5:
                observation, reward, terminated, truncated, info = result
                reset_needed = terminated or truncated
            else:
                observation, reward, reset_needed, info = result


            if reset_needed:
                env.reset()

                simulated_bending = read_finger_bending(env, simulation_calibration)

                previous_sim_bending = simulated_bending

                previous_actual = {finger: simulated_bending[finger] / 100.0 for finger in FINGERS}

                filtered_derivative = {finger: 0.0 for finger in FINGERS}

            row = {
                "time_s": time.monotonic() - start_time,
                "sequence": sequence,
                "glove_data_fresh": int(raw_flexion is not None)
            }

            row["control_frequency_hz"] = CONTROL_FREQUENCY
            row["control_dt_s"] = CONTROL_DT
            row["packet_timeout_s"] = PACKET_TIMEOUT
            row["position_error_gain_P"] = POS_ERROR_GAIN_P
            row["position_error_gain_D"] = POS_ERROR_GAIN_Dt
            row["open_fraction"] = OPEN_FRACTION
            row["closed_fraction"] = CLOSED_FRACTION

            for finger in FINGERS:
                row[f"{finger}_raw"] = (
                    raw_flexion[finger] if raw_flexion is not None else ""
                )

            for finger in FINGERS:
                row[f"{finger}_input_pct"] = flexion[finger] * 100.0

            for finger in FINGERS:
                row[f"{finger}_corrected_pct"] = corrected_flexion[finger] * 100

            for finger in FINGERS:
                row[f"{finger}_simulated_pct"] = simulated_bending[finger]

            csv_writer.writerow(row)


            if time.monotonic() - last_flush_time >= 1.0:
                csv_file.flush()
                last_flush_time = time.monotonic()

            elapsed = time.monotonic() - loop_start

            remaining = CONTROL_DT - elapsed

            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        print("\nSimulation interupted by user.")

    finally:
        if 'csv_file' in locals() and not csv_file.closed:
            csv_file.flush()
            csv_file.close()
        receiver.close()
        env.close()

        print("\nSimulator closed.")

    

if __name__ == "__main__":
    main()



