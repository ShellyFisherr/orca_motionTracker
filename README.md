
Verify executable
```
cd ~/senseglove/senseglove_teleop

ls -lh build/senseglove_reader
```

verify stream implementation
```
grep -n -A30 -B5 'writeBinaryFrame' teleop.cpp
```

create package directory
```
cd ~/orca_project

mkdir -p src/orca_teleop/src/orca_teleop/ingress/senseglove

touch src/orca_teleop/src/orca_teleop/ingress/senseglove/__init__.py
```

open publisher file
```
nano src/orca_teleop/src/orca_teleop/ingress/senseglove/publisher.py
```

verify file
```
python3 -m py_compile \
src/orca_teleop/src/orca_teleop/ingress/senseglove/publisher.py
```


activate orca environment
```
cd ~/orca_project

source .venv/bin/activate
```

Check required packages
```
python -c "import grpc, numpy; print('grpc and numpy OK')"
```

Check adampter import
```
python -c "from orca_motionTracker.Processing.senseglove_adapter import senseglove_to_landmarks; print('Adapter OK')"
```

Check gRPC imports
```
python -c "from orca_teleop.ingress import hand_stream_pb2, hand_stream_pb2_grpc; print('gRPC imports OK')"
```

Check project structure
```text
~/senseglove/
├── SenseGlove-API/
└── senseglove_teleop/
    ├── teleop.cpp
    ├── config.hpp
    ├── CMakeLists.txt
    └── build/
        └── senseglove_reader

~/orca_project/
└── src/
    ├── orca_motionTracker/
    │   └── src/orca_motionTracker/
    │       └── Processing/
    │           └── senseglove_adapter.py
    │
    └── orca_teleop/
        └── src/orca_teleop/
            └── ingress/
                ├── hand_stream_pb2.py
                ├── hand_stream_pb2_grpc.py
                └── senseglove/
                    ├── __init__.py
                    └── publisher.py
```

BUILD

build the C++ reader
```
cd ~/senseglove/senseglove_teleop

CC=clang CXX=clang++ cmake -S . -B build \
    -DCMAKE_BUILD_TYPE=Release

cmake --build build --parallel
```


verify libraries
```
ldd build/senseglove_reader
```

start Orcahand
```
cd ~/orca_project

uv run python -m orca_teleop.server
```


start senseglove publisher
```
cd ~/orca_project

uv run python -m orca_teleop.ingress.senseglove.publisher \
    --reader ~/senseglove/senseglove_teleop/build/senseglove_reader \
    --server localhost:50051 \
    --hand right
```


expected:
```text
Starting SenseGlove reader
Connected to OrcaHand ingress at localhost:50051
Published 60 frames
Published 120 frames
```