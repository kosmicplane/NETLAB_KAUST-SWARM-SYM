# KAUST NETLAB SWARM-SYM - Docker architecture for NVIDIA Brev

This package contains a Brev-ready Docker architecture for running Isaac Sim remotely with GPU acceleration, ROS 2 Jazzy, and Sionna.

## Main containers

The default stack is intentionally separated into three main services:

1. `isaac`: Isaac Sim 5.1.0 with WebRTC livestreaming and the internal ROS 2 Jazzy bridge libraries.
2. `ros2-core`: ROS 2 Jazzy container for swarm control, telemetry, mission nodes, and ROS tooling.
3. `sionna-engine`: Sionna container for radio, coverage, and communication-system experiments.

PX4 remains available as an optional service through the `px4` Compose profile, but it is not started by default.

## What is included

- `compose/docker-compose.yml`: main orchestration for Isaac Sim, ROS 2 Jazzy, Sionna, and optional PX4.
- `compose/fastdds.xml`: Fast DDS UDP profile for Docker/host-network ROS communication.
- `docker/isaacsim/Dockerfile`: Isaac Sim image extension for Brev. It does not apt-install a separate ROS distro inside Isaac.
- `docker/isaacsim/entrypoint.sh`: sets Isaac Sim internal ROS 2 Jazzy bridge library path.
- `docker/ros2/Dockerfile`: ROS 2 Jazzy container based on `ros:jazzy-ros-base-noble`.
- `docker/sionna/Dockerfile`: Sionna container using Ubuntu 24.04 and pinned Python requirements.
- `requirements/`: pinned apt and Python requirements for reproducible builds.
- `workspace/isaac/scripts/basic_swarm_scene.py`: minimal Isaac Sim scene with drones, users, and communication towers for visual validation.
- `scripts/check_brev_gpu.sh`: validates NVIDIA GPU availability from the host and Docker.
- `scripts/run_isaac_sample_scene.sh`: launches the Isaac sample scene inside the running Isaac container.

## Important design decisions

- Everything ROS-facing is Jazzy. The main stack uses Jazzy image names and Jazzy package installs only.
- Isaac Sim uses its internal ROS 2 Jazzy bridge libraries instead of sourcing `/opt/ros/jazzy` inside the Isaac container.
- The external ROS container is the place for normal ROS 2 Jazzy development and control nodes.
- Isaac, ROS 2, and Sionna use host networking to simplify WebRTC and DDS communication on Brev.
- Persistent Isaac Sim cache directories are mounted to reduce startup and shader/cache regeneration overhead.

## Required Brev ports for visualization

Open these ports in the Brev instance security settings/firewall:

```text
49100/tcp
47998/udp
```

Port `8210` is not part of this default compose because there is no separate web-viewer service in this repository.

## Quick start

From the Docker folder:

```bash
cd compose
cp .env.example .env
nano .env
```

Set:

```env
ISAACSIM_HOST=<YOUR_BREV_PUBLIC_IP>
```

Then build and start:

```bash
make prepare-brev
make build
make up
make logs-isaac
```

Connect with the Isaac Sim WebRTC Streaming Client to the public IP of the Brev instance.

## Verify

```bash
make verify-ros2
make verify-sionna
```

## Run the sample visualization scene

After Isaac starts:

```bash
../scripts/run_isaac_sample_scene.sh
```

The sample scene creates:

- Ground plane
- Urban blocks
- 3 drone placeholders
- 2 communication tower placeholders
- User/device points
- Coverage rings

This is only a visual validation scene. It is not yet a full Pegasus/PX4 flight model.

## Service model

Recommended workflow:

1. Start Isaac Sim and validate visualization.
2. Start ROS 2 Jazzy container.
3. Start Sionna for coverage/radio experiments.
4. Connect ROS 2 nodes to Isaac Sim ROS bridge and to Sionna bridge.
5. Add PX4/Pegasus after Isaac + ROS + Sionna are stable.

## Common commands

```bash
cd compose
make ps
make up
make up-isaac
make up-ros2
make up-sionna
make up-px4
make logs-isaac
make shell-isaac
make shell-ros2
make shell-sionna
make down
```
