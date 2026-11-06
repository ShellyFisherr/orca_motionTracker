"""SenseGlove UDP -> OrcaHand gRPC publisher"""

from __future__ import annotations

import argparse
import logging
import time

import grpc
import numpy as np

from orca_teleop.ingress import hand_stream_pb2
from orca_teleop.ingress import hand_stream_pb2_grpc

from orca_motionTracker.Input.senseglove_udp import SenseGloveUDPReceiver
from orca_motionTracker.Processing.senseglove_adapter import senseglove_to_landmarks

logger = logging.getLogger("senseGlove_accepting")

def frame_generator(
        receiver: SenseGloveUDPReceiver,
        handedness: str,
        wrist_position_mm: np.ndarray,
        axis_transform: np.ndarray,):

    last_sequence = -1
    received = 0

    while True:
        frame = receiver.receive()

        if frame == None:
            continue


        if frame.sequence <= last_sequence:
            logger.warning("Ignore old packet sequence %d",
                           frame.sequence)
            continue

        last_sequence = frame.sequence

        try:
            landmarks = senseglove_to_landmarks(
                frame.positions_mm,
                wrist_position_mm,
                axis_transform,)

        except ValueError as exc:
            logger.warning("Could not convert sequence %d: %s",
                           frame.sequence,
                           exc,)
            continue

        received += 1

        if received % 60 == 0:
            logger.info(
                "Received %d frames | sequence %d",
                received,
                frame.sequence,)

        yield hand_stream_pb2.HandFrame(
            keypoints=landmarks.reshape(-1).tolist(),
            handedness=handedness,
            timestamp_ns=time.time_ns(),)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--udp-host",
                        default="0.0.0.0")

    parser.add_argument("--udp-port",
                        type=int,
                        default=5010,)

    parser.add_argument("--server",
                        default="localhost:50051",
                        help="orca_teleop gRPC server address",)

    parser.add_argument("--hand",
                        choices=["left", "right"],
                        default="right",)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",)

    # IMPORTANT
    # replace with actual calibrated wrist position and
    # coordinate transform once SDK frame is verified

    wrist_position_mm = np.array(
        [0.0, 0.0, 0.0],
        dtype=np.float32,)

    axis_transform = np.eye(3, dtype=np.float32)

    receiver = SenseGloveUDPReceiver(
        host=args.udp_host,
        port=args.udp_port,)

    channel = grpc.insecure_channel(args.server)

    stub = hand_stream_pb2_grpc.HandStreamStub(channel)

    logger.info("Connecting to OrcaHand ingress at %s", args.server)


    try:
        summary = stub.StreamHandFrames(
            frame_generator(
                receiver,
                args.hand,
                wrist_position_mm,
                axis_transform,))

        logger.info("Stream ended. Frames accepted: %d",
                    summary.frames_received)

    except KeyboardInterrupt:
        logger.info("Stopping SenseGlove receiver...")

    except grpc.RpcError:
        logger.exception("gRPC conncetion failed")

    finally:
        receiver.close()
        channel.close()


if __name__ == "__main__":
    main()


