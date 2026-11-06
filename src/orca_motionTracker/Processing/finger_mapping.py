FINGER_ACTUATORS = {
    "thumb": [1, 3, 4],
    "index": [6, 7],
    "middle": [9, 10],
    "ring": [12, 13],
    "pinky": [15, 16]
}

FINGERS = [
    "thumb",
    "index",
    "middle",
    "ring",
    "pinky"
]

FINGER_JOINTS = {
    "thumb": [
        "right_thumb_mcp",
        "right_thumb_pip",
        "right_thumb_dip"
    ],
    "index": [
        "right_index_mcp",
        "right_index_pip"
    ],
    "middle": [
        "right_middle_mcp",
        "right_middle_pip"
    ],
    "ring": [
        "right_ring_mcp",
        "right_ring_pip"
    ],
    "pinky": [
        "right_pinky_mcp",
        "right_pinky_pip"
    ]
}

# Finger actuators are only the actuators that bend the finger, 
# not the actuators that move the finger sideways. 
# The actuators that move the finger sideways (2, 5, 7, 11, 14) are not included in this mapping.

# 2  = thumb abduction
# 5  = index abduction
# 8  = middle abduction
# 11 = ring abduction
# 14 = pinky abduction