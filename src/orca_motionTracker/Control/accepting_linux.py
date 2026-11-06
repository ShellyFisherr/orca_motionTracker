"""SenseGlove C++ reader -> OrcaHand gRPC publisher."""

from __future__ import annotations

import argparse
import logging
import struct
import subprocess
import time
from pathlib import Path

import grpc
import numpy as np

from orca_teleop.ingress import hand_stream_pb2
from orca_teleop.ingress import hand_stream_pb2_grpc

from orca_motionTracker.Processing.senseglove_adapter import (
    senseglove_to_landmarks,
)


logger = logging.getLogger("senseglove_publisher")

# uint64 timestamp + 60 floats
FRAME_FORMAT = "<Q60f"
FRAME_SIZE = struct.calcsize(FRAME_FORMAT)


def read_exact(stream, size: int) -> bytes | None:
    """Read exactly size bytes from a binary stream."""

    data = bytearray()

    while len(data) < size:
        chunk = stream.read(size - len(data))

        if not chunk:
            if not data:
                return None

            raise RuntimeError(
                f"Incomplete binary frame: received {len(data)} "
                f"of {size} bytes"
            )

        data.extend(chunk)

    return bytes(data)


def start_reader(executable: Path) -> subprocess.Popen:
    """Start the SenseGlove C++ reader."""

    if not executable.is_file():
        raise FileNotFoundError(
            f"SenseGlove reader not found: {executable}"
        )

    logger.info("Starting SenseGlove reader: %s", executable)

    process = subprocess.Popen(
        [str(executable), "--stream"],
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0,
    )

    if process.stdout is None:
        process.terminate()
        raise RuntimeError("Could not open reader stdout")

    return process


def frame_generator(
    process: subprocess.Popen,
    handedness: str,
    wrist_position_mm: np.ndarray,
    axis_transform: np.ndarray,
):
    """Read C++ frames, convert them to landmarks and yield gRPC messages."""

    if process.stdout is None:
        raise RuntimeError("Reader stdout is unavailable")

    received = 0

    while True:

        # Read one complete binary record.
        raw = read_exact(process.stdout, FRAME_SIZE)

        if raw is None:
            return

        values = struct.unpack(FRAME_FORMAT, raw)

        reader_timestamp_ns = values[0]

        # Five fingers, four joints per finger, XYZ coordinates.
        positions = np.asarray(
            values[1:],
            dtype=np.float32,
        ).reshape(5, 4, 3)

        try:
            landmarks = senseglove_to_landmarks(
                [positions[i] for i in range(5)],
                wrist_position_mm,
                axis_transform,
            )

        except ValueError as exc:
            logger.warning(
                "Could not convert frame: %s",
                exc,
            )
            continue

        received += 1

        if received % 60 == 0:
            logger.info(
                "Published %d frames | C++ timestamp: %d",
                received,
                reader_timestamp_ns,
            )

        yield hand_stream_pb2.HandFrame(
            keypoints=landmarks.reshape(-1).tolist(),
            handedness=handedness,
            timestamp_ns=time.time_ns(),
            wrist_angle_degrees=0.0,
        )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--reader",
        type=Path,
        default=(
            Path.home()
            / "senseglove/senseglove_teleop/build/senseglove_reader"
        ),
        help="Path to the compiled SenseGlove C++ reader",
    )

    parser.add_argument(
        "--server",
        default="localhost:50051",
        help="OrcaHand gRPC server address",
    )

    parser.add_argument(
        "--hand",
        choices=["left", "right"],
        default="right",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    # Initial coordinate configuration.
    # Calibrate these after inspecting real glove measurements.
    wrist_position_mm = np.zeros(3, dtype=np.float32)
    axis_transform = np.eye(3, dtype=np.float32)

    process = None
    channel = None
    call = None

    try:

        # Start the C++ SenseGlove reader.
        process = start_reader(args.reader)

        # Connect to the existing OrcaHand ingress.
        channel = grpc.insecure_channel(args.server)

        grpc.channel_ready_future(channel).result(timeout=10)

        stub = hand_stream_pb2_grpc.HandStreamStub(channel)

        logger.info(
            "Connected to OrcaHand ingress at %s",
            args.server,
        )

        # Stream landmarks to OrcaHand.
        call = stub.StreamHandFrames.future(
            frame_generator(
                process,
                args.hand,
                wrist_position_mm,
                axis_transform,
            )
        )

        summary = call.result()

        logger.info(
            "Stream ended. Frames accepted: %d",
            summary.frames_received,
        )

    except KeyboardInterrupt:
        logger.info("Stopping SenseGlove publisher...")

    except grpc.RpcError:
        logger.exception("OrcaHand gRPC connection failed")

    except Exception:
        logger.exception("SenseGlove publisher failed")

    finally:

        if call is not None:
            call.cancel()

        if process is not None:

            if process.poll() is None:
                process.terminate()

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            logger.info(
                "SenseGlove reader stopped (exit code %s)",
                process.returncode,
            )

        if channel is not None:
            channel.close()


if __name__ == "__main__":
    main()