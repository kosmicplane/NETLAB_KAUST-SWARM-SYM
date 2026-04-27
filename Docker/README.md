# KAUST NETLAB SWARM-SYM - Docker architecture for NVIDIA Brev

This package contains a Brev-ready Docker architecture for running Isaac Sim remotely with GPU acceleration and visualization through Isaac Sim WebRTC/headless streaming.

## What is included

- `compose/docker-compose.yml`: main orchestration for Isaac Sim, ROS 2, PX4 SITL, and Sionna.
- `docker/isaacsim/Dockerfile`: Isaac Sim image extension for Brev, ROS 2 Humble tools, and project utilities.
- `docker/isaacsim/entrypoint.sh`: environment setup for Isaac Sim + ROS 2.
- `docker/ros2/Dockerfile`: ROS 2 Humble container for swarm control nodes.
- `docker/PX4/Dockerfile`: PX4 SITL development container.
- `docker/sionna/Dockerfile`: Sionna container with NVIDIA GPU support.
- `workspace/isaac/scripts/basic_swarm_scene.py`: minimal Isaac Sim scene with drones, users, and communication towers for visual validation.
- `scripts/check_brev_gpu.sh`: validates NVIDIA GPU availability from the host and from Docker.
- `scripts/run_isaac_sample_scene.sh`: launches the Isaac sample scene inside the running Isaac container.

## Design decision

This package intentionally does **not** mount persistent Isaac Sim cache directories. Only project files, scripts, data, and results are mounted. Isaac Sim may take longer to start because shader/cache data will be regenerated when containers are recreated.

## Recommended Brev instance

Use a GPU with RTX/RT cores, for example L40S, RTX 6000 Ada, or RTX PRO-class GPUs. Avoid A100/H100 for Isaac Sim visualization because they do not provide the RTX rendering path expected by Isaac Sim.

## Required Brev ports for visualization

Open these ports in the Brev instance security settings/firewall:

```text
8210
49100
47998
```

Use Isaac Sim WebRTC Streaming Client or the web viewer supported by your Isaac Sim version. The default Isaac service runs headless using `/isaac-sim/runheadless.sh -v`.

## Quick start

From the root of this package:

```bash
cd compose
cp .env.example .env
../scripts/check_brev_gpu.sh
make build
make up-isaac
```

Watch the logs:

```bash
make logs-isaac
```

Then connect using Isaac Sim WebRTC to the public IP of the Brev instance.

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
2. Start ROS 2 container.
3. Start PX4 SITL if needed.
4. Start Sionna for coverage/radio experiments.
5. Connect ROS 2 nodes to Isaac Sim ROS bridge and to Sionna bridge.

## Common commands

```bash
cd compose
make ps
make up-isaac
make up-ros2
make up-px4
make up-sionna
make logs-isaac
make shell-isaac
make down
```

## Important notes

- Do not run Isaac Sim and Pegasus as two separate Isaac-based visualization containers at the same time unless you know exactly why. Prefer one Isaac Sim container and install/mount Pegasus as an extension or workspace inside it.
- The `isaac` service uses `network_mode: host` and `ipc: host` to simplify WebRTC and ROS 2 communication on Brev.
- The `ros2-core` service also uses host networking for DDS discovery.
- The Dockerfiles are intentionally separated: Isaac Sim, ROS 2, PX4, and Sionna have different runtime requirements.
