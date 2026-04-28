# Changes in this Jazzy/Brev-ready version

## Main goal

Keep the whole ROS-facing stack on ROS 2 Jazzy while making the Docker architecture better suited for NVIDIA Brev and Isaac Sim WebRTC streaming.

## Modified files

- `Docker/compose/docker-compose.yml`
  - Updated the existing compose file instead of creating a new one.
  - Changed ROS image defaults to Jazzy.
  - Added Isaac Sim WebRTC public IP and port variables.
  - Added Isaac Sim ROS 2 Bridge startup flag.
  - Added persistent Isaac cache/config/log mounts.
  - Added Fast DDS profile mount.
  - Kept PX4 but moved it to an optional Compose profile.

- `Docker/compose/.env.example` and `Docker/compose/.env`
  - Added `ROS_DISTRO=jazzy`.
  - Changed `ROS2_IMAGE` to `netlab-ros2-jazzy:brev`.
  - Added `ISAACSIM_HOST`, `ISAACSIM_SIGNAL_PORT`, and `ISAACSIM_STREAM_PORT`.

- `Docker/docker/ros2/Dockerfile`
  - Uses `ros:jazzy-ros-base-noble`.
  - Uses `ros-jazzy-*` packages only.
  - Sources `/opt/ros/jazzy/setup.bash`.

- `Docker/docker/isaacsim/Dockerfile`
  - Removed external ROS installation inside Isaac.
  - Keeps Isaac Sim clean and lets the entrypoint use the internal Jazzy bridge libraries.

- `Docker/docker/isaacsim/entrypoint.sh`
  - Sets `ROS_DISTRO=jazzy`.
  - Adds `/isaac-sim/exts/isaacsim.ros2.bridge/jazzy/lib` to `LD_LIBRARY_PATH`.
  - Does not source `/opt/ros/*` by default.

- `Docker/docker/pegasus/Dockerfile`
  - Updated the helper environment to Jazzy only.

- `Docker/docker/sionna/Dockerfile`
  - Uses Ubuntu 24.04 CUDA base image.
  - Installs pinned requirements from `Docker/requirements/sionna-requirements.txt`.

- `Docker/requirements/`
  - Added pinned apt/Python requirement files for ROS 2 Jazzy, Isaac helper scripts, and Sionna.

- `Docker/compose/Makefile`
  - Added `prepare-brev`, `verify-ros2`, and `verify-sionna` targets.
  - `make up` starts only Isaac, ROS 2, and Sionna by default.
  - `make up-px4` starts PX4 explicitly through a Compose profile.

## Expected default runtime layout

```text
Brev VM
├── isaac-sim             Isaac Sim 5.1.0 + internal ROS 2 Jazzy Bridge + WebRTC
├── netlab-ros2-core      ROS 2 Jazzy / swarm control / telemetry / mission logic
└── netlab-sionna-engine  Sionna / radio / coverage / telecom metrics
```

PX4 remains available but optional.
