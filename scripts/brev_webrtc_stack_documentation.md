# NETLAB KAUST SWARM-SYM: Brev, Docker, ROS 2 Jazzy, Sionna and Isaac Sim WebRTC Runbook

**Project:** NETLAB KAUST SWARM-SYM  
**Purpose:** Reproducible cloud execution and visualization workflow for the swarm simulation stack.  
**Target environment:** NVIDIA Brev GPU VM, Docker Compose, Isaac Sim 5.1.0, ROS 2 Jazzy, Sionna, Tailscale, Isaac Sim WebRTC Streaming Client.  
**Primary script:** `scripts/netlab_brev_webrtc.sh`  
**Important convention:** The folder name is `scripts/` in lowercase and plural.

---

## 1. Executive Summary

This document describes how to reproduce the working cloud simulation setup used for the NETLAB KAUST SWARM-SYM project. The stack is designed to run the heavy simulation workload on an NVIDIA Brev GPU virtual machine while allowing the researcher to interact with Isaac Sim remotely through the Isaac Sim WebRTC Streaming Client.

The final architecture separates the system into three main Docker services:

1. `isaac`: Isaac Sim 5.1.0 running headless with WebRTC streaming enabled.
2. `ros2-core`: ROS 2 Jazzy container for control, orchestration, topic inspection, and future swarm coordination nodes.
3. `sionna-engine`: Sionna container for wireless/channel simulation and radio propagation computation.

Tailscale is used to create a stable private network path between the local PC and the Brev VM. This avoids the UDP/NAT issues that initially caused Isaac Sim WebRTC to connect but display a black screen. The WebRTC stream uses:

- `TCP 49100` for signaling.
- `UDP 47998` for media/video streaming.
- NVENC on the remote NVIDIA GPU for hardware video encoding.

The workflow has been consolidated into one executable script:

```bash
./scripts/netlab_brev_webrtc.sh
```

The script does not replace the Docker Compose architecture. It standardizes and automates the operational steps required to configure, build, run, verify, and diagnose the complete stack.

---

## 2. Design Rationale

### 2.1 Why Brev?

The local machine can be used for development, Git operations, editing, and running the WebRTC client. However, Isaac Sim with RTX rendering and NVENC streaming requires GPU resources that are better provided by a remote GPU VM. Brev provides access to NVIDIA GPU machines such as the L40S, which is suitable for Isaac Sim streaming because it supports NVENC.

### 2.2 Why Docker Compose?

The project requires multiple runtime layers that should remain isolated:

- Isaac Sim is GPU-heavy and has its own NVIDIA/Omniverse runtime requirements.
- ROS 2 Jazzy should remain clean and independent for robotics middleware and control logic.
- Sionna has its own Python/TensorFlow/radio-simulation dependency structure.

Docker Compose provides a reproducible way to define, build, start, stop, and inspect these services from a single configuration file.

### 2.3 Why Tailscale?

Direct public-IP WebRTC streaming initially failed because the server attempted to send UDP traffic to a private local address such as `192.168.x.x`, which is not routable from the Brev VM. Tailscale assigns stable `100.x.y.z` addresses to both the local PC and Brev VM, creating a private route that supports the WebRTC traffic path reliably.

### 2.4 Why ROS 2 Jazzy?

The project standard is ROS 2 Jazzy. The setup must not be downgraded to Humble. Jazzy is the required distribution for this project architecture and is the expected ROS layer inside the `ros2-core` container.

---

## 3. System Architecture

```text
+------------------------------+        Tailscale private network        +--------------------------------+
| Local PC                     |  <----------------------------------->  | NVIDIA Brev VM                  |
|                              |                                         |                                |
| - Git repository clone       |                                         | - Docker Engine                 |
| - WebRTC Client 1.1.5        |                                         | - NVIDIA Container Toolkit      |
| - Tailscale client           |                                         | - Tailscale client              |
|                              |                                         |                                |
| Connects to:                 |                                         | Docker Compose services:        |
|   Brev Tailscale IP          |                                         |   1. isaac                      |
|   e.g., 100.72.58.116        |                                         |   2. ros2-core                  |
|                              |                                         |   3. sionna-engine              |
+------------------------------+                                         +--------------------------------+
```

The Isaac Sim user interface is rendered on the Brev GPU, encoded through NVENC, and streamed through WebRTC to the local PC. The local PC does not need to render Isaac Sim natively; it only needs to run the Isaac Sim WebRTC Streaming Client.

---

## 4. Repository Conventions

The script must live at:

```bash
scripts/netlab_brev_webrtc.sh
```

Do not use:

```bash
Scripts/netlab_brev_webrtc.sh
script/netlab_brev_webrtc.sh
```

Linux paths are case-sensitive, so `scripts/`, `Scripts/`, and `script/` are three different paths.

After cloning or modifying the repository, always ensure the script is executable:

```bash
chmod +x scripts/netlab_brev_webrtc.sh
```

---

## 5. Primary Script Overview

The operational script is:

```bash
./scripts/netlab_brev_webrtc.sh
```

It supports the following modes:

| Mode | Environment | Purpose | When to use |
|---|---|---|---|
| `setup-brev` | Brev VM | Installs/checks Tailscale, updates `.env`, validates Docker GPU access | First time on a new Brev VM, or after deleting/recreating the VM |
| `build-stack` | Brev VM | Builds/rebuilds ROS 2 Jazzy and Sionna Docker services; checks Isaac build/pull path | After cloning repo, after changing Dockerfiles, requirements, or service build context |
| `start-stack` | Brev VM | Starts Isaac, ROS 2, and Sionna together; waits for Isaac streaming readiness | Normal full-stack startup |
| `start-brev` | Brev VM | Recreates only the Isaac service and waits for WebRTC readiness | When only Isaac/WebRTC changed |
| `doctor-stack` | Brev VM | Runs full diagnostics across Isaac/WebRTC, ROS 2, and Sionna | When something fails or before reporting a bug |
| `doctor-brev` | Brev VM | Focused diagnostics for GPU, Tailscale, ports, Isaac logs, and NVENC | When Isaac streaming is failing |
| `ros-check` | Brev VM | Checks ROS 2 Jazzy container, topics, and nodes | When validating the ROS layer |
| `sionna-check` | Brev VM | Checks Sionna container and Python import | When validating the Sionna layer |
| `monitor-brev` | Brev VM | Prints monitoring commands for logs, tcpdump, and NVENC | During live debugging |
| `doctor-local` | Local PC | Checks local Tailscale and WebRTC client file | Before launching the local client |
| `start-local` | Local PC | Starts the Isaac Sim WebRTC Streaming Client cleanly | Every time you want to connect to Isaac Sim remotely |

---

## 6. Environment Variables Used by the Script

The script supports environment overrides. In normal use, the defaults are sufficient.

| Variable | Default | Purpose |
|---|---|---|
| `PROJECT_ROOT` | `$HOME/workspace/NETLAB` | Root folder of the repository on Brev |
| `COMPOSE_DIR` | `$PROJECT_ROOT/Docker/compose` | Docker Compose directory |
| `COMPOSE_FILE` | `docker-compose.yml` | Compose file name |
| `ENV_FILE` | `.env` | Compose environment file |
| `ISAAC_SERVICE` | `isaac` | Isaac Compose service name |
| `ISAAC_CONTAINER` | `isaac-sim` | Isaac container name |
| `ROS_SERVICE` | `ros2-core` | ROS Compose service name |
| `ROS_CONTAINER` | `netlab-ros2-core` | ROS container fallback name |
| `SIONNA_SERVICE` | `sionna-engine` | Sionna Compose service name |
| `SIONNA_CONTAINER` | `netlab-sionna-engine` | Sionna container fallback name |
| `WEBRTC_CLIENT` | `$HOME/Downloads/isaacsim-webrtc-streaming-client-1.1.5-linux-x64.AppImage` | Local WebRTC client path |
| `WEBRTC_CACHE_DIR` | `/tmp/isaac-webrtc-clean` | Temporary clean profile for the WebRTC client |
| `ISAAC_READY_TIMEOUT` | `600` | Maximum time in seconds to wait for Isaac readiness |

Example override:

```bash
PROJECT_ROOT=$HOME/workspace/NETLAB \
COMPOSE_DIR=$HOME/workspace/NETLAB/Docker/compose \
./scripts/netlab_brev_webrtc.sh doctor-stack
```

---

## 7. Required `.env` Values

Inside:

```bash
Docker/compose/.env
```

The key values should be:

```env
ROS_DISTRO=jazzy
ROS_DOMAIN_ID=42
RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ISAACSIM_HOST=<BREV_TAILSCALE_IP>
ISAACSIM_SIGNAL_PORT=49100
ISAACSIM_STREAM_PORT=47998
ISAACSIM_TAG=5.1.0
```

For the first successful run, the Brev Tailscale IP was:

```env
ISAACSIM_HOST=100.72.58.116
```

On a new Brev VM, this value may change. The script mode `setup-brev` detects the current Brev Tailscale IPv4 and updates `.env` automatically.

---

## 8. Required Isaac Sim Compose Configuration

The Isaac service should expose NVIDIA GPU capabilities and use the Isaac 5.x WebRTC livestream flags.

### 8.1 Required NVIDIA Environment

Inside the `isaac` service:

```yaml
environment:
  ACCEPT_EULA: "Y"
  PRIVACY_CONSENT: "Y"
  NVIDIA_VISIBLE_DEVICES: all
  NVIDIA_DRIVER_CAPABILITIES: all
```

`NVIDIA_DRIVER_CAPABILITIES=all` is important because streaming requires graphics/video capabilities in addition to compute.

### 8.2 Required Livestream Command

The working Isaac Sim 5.1.0 streaming command should use:

```yaml
command:
  - /isaac-sim/runheadless.sh
  - -v
  - --/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge
  - --/app/livestream/publicEndpointAddress=${ISAACSIM_HOST:-127.0.0.1}
  - --/app/livestream/port=${ISAACSIM_SIGNAL_PORT:-49100}
  - --/persistent/app/window/width=1280
  - --/persistent/app/window/height=720
  - --/app/window/dpiScaleOverride=1.0
  - --/app/window/scaleToMonitor=false
```

Avoid mixing old and new livestream flags unless intentionally debugging. The script warns if rendered Compose still contains older `primaryStream` flags.

---

## 9. First-Time Setup on a New Brev VM

Use this workflow when the Brev VM is new, deleted/recreated, or does not yet have the project configured.

### 9.1 Connect to Brev

From the local PC:

```bash
ssh netlab-kaust
```

If the hostname differs, use the correct Brev SSH target.

### 9.2 Clone the Repository

On Brev:

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone git@github.com:kosmicplane/NETLAB_KAUST-SWARM-SYM.git NETLAB
cd NETLAB
```

If SSH is not configured, either create a GitHub SSH key for the VM or clone using HTTPS with a token. SSH setup is outside the scope of the runtime script.

### 9.3 Make the Script Executable

```bash
chmod +x scripts/netlab_brev_webrtc.sh
```

### 9.4 Run Brev Setup

```bash
./scripts/netlab_brev_webrtc.sh setup-brev
```

This performs the following operations:

1. Checks for Docker and `curl`.
2. Installs Tailscale if it is missing.
3. Runs `sudo tailscale up --hostname netlab-kaust-brev` if Tailscale is not authenticated.
4. Detects the Brev Tailscale IPv4 address.
5. Updates `.env` with:
   - `ROS_DISTRO=jazzy`
   - `ISAACSIM_HOST=<BREV_TAILSCALE_IP>`
   - `ISAACSIM_SIGNAL_PORT=49100`
   - `ISAACSIM_STREAM_PORT=47998`
   - `ISAACSIM_TAG=5.1.0`
6. Tests Docker GPU access with an NVIDIA CUDA container.
7. Attempts to configure NVIDIA Container Toolkit if Docker GPU access fails.
8. Prints Compose services and final `.env` values.

### 9.5 Build the Stack

```bash
./scripts/netlab_brev_webrtc.sh build-stack
```

Use this after cloning or after changing Dockerfiles, Python requirements, ROS dependencies, Sionna dependencies, or service build contexts.

### 9.6 Start the Stack

```bash
./scripts/netlab_brev_webrtc.sh start-stack
```

This starts all services and waits for the Isaac readiness line:

```text
Isaac Sim Full Streaming App is loaded.
```

Do not connect the WebRTC client before this readiness line appears.

### 9.7 Diagnose the Full Stack

```bash
./scripts/netlab_brev_webrtc.sh doctor-stack
```

Run this after startup to validate the full system state.

---

## 10. Normal Daily Startup

Use this when Brev already has the repository, Tailscale is authenticated, and the stack has already been built.

On Brev:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-stack
```

On the local PC:

```bash
cd ~/Desktop/KAUST/NETLAB_KAUST-SWARM-SYM
./scripts/netlab_brev_webrtc.sh start-local
```

In the WebRTC Client, connect to the Brev Tailscale IP shown by the Brev script, for example:

```text
100.72.58.116
```

Do not add `http://`, do not add a port, and do not use the public Brev IP unless intentionally debugging a non-Tailscale path.

---

## 11. Workflow After Deleting Only Docker Containers

If only Docker containers were removed, the VM still has the repository, Tailscale, Docker, and configuration files.

Use:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-stack
```

If images were also removed or dependencies changed:

```bash
./scripts/netlab_brev_webrtc.sh build-stack
./scripts/netlab_brev_webrtc.sh start-stack
```

You do not need to recreate SSH keys or clone the repository again unless the repository directory was deleted.

---

## 12. Workflow After Deleting the Entire Brev VM

If the Brev VM itself is deleted, all local VM state is gone. You need to:

1. Create or access a new Brev instance.
2. Configure GitHub access if cloning through SSH.
3. Clone the repository.
4. Authenticate Tailscale on the new VM.
5. Run the setup/build/start sequence.

Full sequence:

```bash
ssh netlab-kaust

mkdir -p ~/workspace
cd ~/workspace
git clone git@github.com:kosmicplane/NETLAB_KAUST-SWARM-SYM.git NETLAB
cd NETLAB

chmod +x scripts/netlab_brev_webrtc.sh

./scripts/netlab_brev_webrtc.sh setup-brev
./scripts/netlab_brev_webrtc.sh build-stack
./scripts/netlab_brev_webrtc.sh start-stack
./scripts/netlab_brev_webrtc.sh doctor-stack
```

The new VM may receive a different Tailscale IP. The `setup-brev` mode will update `.env` accordingly.

---

## 13. Local PC Usage

The local PC is responsible for:

- Running the Isaac Sim WebRTC Streaming Client.
- Maintaining local Tailscale connectivity.
- Optionally editing the repository and pushing changes to GitHub.

### 13.1 Local Diagnostics

```bash
./scripts/netlab_brev_webrtc.sh doctor-local
```

This checks:

- Local Tailscale IP.
- Tailscale status.
- Public IPv4.
- Presence of the WebRTC AppImage.

### 13.2 Start WebRTC Client

```bash
./scripts/netlab_brev_webrtc.sh start-local
```

This performs a clean local client launch:

1. Kills old Isaac WebRTC client processes.
2. Removes the temporary clean WebRTC profile.
3. Makes the AppImage executable.
4. Starts the client with:

```bash
--no-sandbox
--ozone-platform=x11
--user-data-dir=/tmp/isaac-webrtc-clean
```

If the client UI itself fails due to local graphical issues, manually try:

```bash
~/Downloads/isaacsim-webrtc-streaming-client-1.1.5-linux-x64.AppImage \
  --no-sandbox \
  --ozone-platform=x11 \
  --use-gl=angle \
  --use-angle=swiftshader \
  --enable-unsafe-swiftshader \
  --user-data-dir=/tmp/isaac-webrtc-clean
```

---

## 14. Diagnostic Philosophy

The setup should be debugged layer by layer. Do not randomly change Docker, ROS, Isaac, and network settings at the same time.

Recommended order:

1. Confirm Brev GPU and Docker GPU access.
2. Confirm Tailscale IPs on both machines.
3. Confirm `.env` uses Brev Tailscale IP.
4. Confirm Compose services render correctly.
5. Confirm Isaac reaches readiness.
6. Confirm TCP 49100 and UDP 47998 traffic over `tailscale0`.
7. Confirm NVENC encoder session appears after client connects.
8. Confirm ROS 2 Jazzy container works.
9. Confirm Sionna import works.

---

## 15. Monitoring Commands

The script prints these through:

```bash
./scripts/netlab_brev_webrtc.sh monitor-brev
```

For deeper manual debugging, open three Brev terminals.

### Terminal A: Isaac Logs

```bash
docker logs -f isaac-sim
```

Wait for:

```text
Isaac Sim Full Streaming App is loaded.
```

### Terminal B: WebRTC Traffic Over Tailscale

```bash
sudo tcpdump -ni tailscale0 '(tcp port 49100 or udp port 47998)'
```

Good pattern:

```text
100.x.x.x:49100 <-> 100.y.y.y
100.x.x.x:47998 <-> 100.y.y.y
```

Bad pattern previously observed:

```text
172.x.x.x:47998 -> 192.168.x.x
```

The bad pattern means Isaac is trying to send UDP video to a private address not reachable from Brev.

### Terminal C: NVENC Sessions

```bash
watch -n 1 "nvidia-smi encodersessions; echo; nvidia-smi --query-gpu=utilization.gpu,utilization.encoder,utilization.decoder,memory.used --format=csv"
```

An encoder session should appear after the WebRTC Client connects successfully.

---

## 16. Troubleshooting Matrix

| Symptom | Likely cause | Command to run | Corrective action |
|---|---|---|---|
| WebRTC client opens but stays black | Isaac not ready, wrong IP, no NVENC session, or media path problem | `docker logs -f isaac-sim`, `nvidia-smi encodersessions`, `tcpdump` | Wait for readiness, verify Tailscale IP, verify encoder session |
| Client connects then disconnects | Media negotiation succeeded but video frames not produced or not routed | `nvidia-smi encodersessions` | Verify Isaac livestream flags and NVIDIA capabilities |
| UDP goes to `192.168.x.x` | NAT/local private IP selected | `sudo tcpdump -ni any '(tcp port 49100 or udp port 47998)'` | Use Tailscale and connect to Brev `100.x.x.x` IP |
| `No such file or directory` for script | Wrong folder casing/name | `ls scripts/netlab_brev_webrtc.sh` | Use `scripts/`, lowercase plural |
| Compose fails due to duplicated YAML key | Duplicate environment variables | `docker compose config` | Remove duplicated keys such as `NVIDIA_VISIBLE_DEVICES` |
| ROS check fails | ROS container not running or Jazzy missing | `./scripts/netlab_brev_webrtc.sh ros-check` | Build/start stack; confirm Dockerfile uses Jazzy |
| Sionna check fails | Sionna container not running or Python dependency missing | `./scripts/netlab_brev_webrtc.sh sionna-check` | Rebuild `sionna-engine` and inspect logs |
| AppImage sandbox error | Chromium/Electron sandbox issue | `start-local` or manual flags | Use `--no-sandbox --ozone-platform=x11` |
| Isaac shows `Waiting for RtPso async group async compilation` | RTX shader warmup | `docker logs -f isaac-sim` | Wait; do not connect before readiness line |

---

## 17. Explanation of Each Script Mode

### 17.1 `setup-brev`

Use on a new Brev VM or after major environment reset.

```bash
./scripts/netlab_brev_webrtc.sh setup-brev
```

It prepares the Brev-side runtime. It does not launch the full simulation. It is safe to run more than once because it updates `.env` idempotently.

Use it when:

- A new Brev VM has been created.
- Tailscale is not installed or not authenticated.
- `.env` has the wrong `ISAACSIM_HOST`.
- Docker GPU access has not been validated.

### 17.2 `build-stack`

Use after changes to Dockerfiles, dependencies, build contexts, or a fresh clone.

```bash
./scripts/netlab_brev_webrtc.sh build-stack
```

It builds:

- `ros2-core`
- `sionna-engine`
- `isaac` if the Compose service supports building, otherwise it continues if Isaac uses a prebuilt image.

### 17.3 `start-stack`

Use for standard operation.

```bash
./scripts/netlab_brev_webrtc.sh start-stack
```

It starts all services with `docker compose up -d --build`, waits for Isaac readiness, and then runs ROS/Sionna checks.

### 17.4 `start-brev`

Use when only Isaac needs to be recreated.

```bash
./scripts/netlab_brev_webrtc.sh start-brev
```

This is useful after changing Isaac livestream flags, Isaac environment variables, or WebRTC-related configuration.

### 17.5 `doctor-brev`

Use when Isaac/WebRTC fails.

```bash
./scripts/netlab_brev_webrtc.sh doctor-brev
```

It checks:

- Host identity.
- Tailscale IP/status.
- NVIDIA host GPU.
- Docker GPU access.
- Compose services.
- `.env` values.
- Isaac NVIDIA environment.
- NVENC/NVDEC libraries.
- Listening ports.
- Encoder sessions.
- GPU usage.
- Recent Isaac streaming logs.
- ROS Jazzy basic check.

### 17.6 `doctor-stack`

Use for full-stack debugging.

```bash
./scripts/netlab_brev_webrtc.sh doctor-stack
```

This wraps:

- `doctor-brev`
- `ros-check`
- `sionna-check`
- Compose status
- Recent logs for Isaac, ROS, and Sionna

Use this before documenting a problem or asking for help.

### 17.7 `ros-check`

Use to validate the ROS layer.

```bash
./scripts/netlab_brev_webrtc.sh ros-check
```

It verifies:

- `/opt/ros/jazzy/setup.bash` exists.
- `ROS_DISTRO=jazzy`.
- ROS 2 topics can be listed.
- ROS 2 nodes can be listed.

### 17.8 `sionna-check`

Use to validate the Sionna layer.

```bash
./scripts/netlab_brev_webrtc.sh sionna-check
```

It verifies:

- Python is available.
- `import sionna` succeeds.
- Sionna version can be printed if exposed by the package.

### 17.9 `start-local`

Use on the local PC to start the Isaac Sim WebRTC Streaming Client.

```bash
./scripts/netlab_brev_webrtc.sh start-local
```

This should not be run inside Brev. It is intended for the laptop or workstation.

### 17.10 `doctor-local`

Use on the local PC before opening the client.

```bash
./scripts/netlab_brev_webrtc.sh doctor-local
```

It validates Tailscale and the WebRTC client file path.

---

## 18. Recommended Operational Checklists

### 18.1 Full New Brev Setup

```bash
ssh netlab-kaust
cd ~/workspace
git clone git@github.com:kosmicplane/NETLAB_KAUST-SWARM-SYM.git NETLAB
cd NETLAB
chmod +x scripts/netlab_brev_webrtc.sh
./scripts/netlab_brev_webrtc.sh setup-brev
./scripts/netlab_brev_webrtc.sh build-stack
./scripts/netlab_brev_webrtc.sh start-stack
./scripts/netlab_brev_webrtc.sh doctor-stack
```

### 18.2 Normal Start

Brev:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-stack
```

Local PC:

```bash
cd ~/Desktop/KAUST/NETLAB_KAUST-SWARM-SYM
./scripts/netlab_brev_webrtc.sh start-local
```

### 18.3 Quick Debug

Brev:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh doctor-stack
```

### 18.4 Rebuild After Docker Changes

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh build-stack
./scripts/netlab_brev_webrtc.sh start-stack
```

### 18.5 Only Restart Isaac

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-brev
```

---

## 19. Shutdown and Restart Guidance

To close Isaac cleanly, use the streamed Isaac Sim interface:

```text
File -> Exit
```

Then close the WebRTC client window.

To stop containers:

```bash
cd ~/workspace/NETLAB/Docker/compose
docker compose --env-file .env -f docker-compose.yml down
```

To restart later:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-stack
```

---

## 20. Security and Operational Notes

1. Do not commit private SSH keys, tokens, passwords, or personal credentials.
2. Verify `.env` before pushing if it ever contains secrets.
3. Tailscale authentication is interactive and cannot be fully automated safely without an auth key.
4. Only one WebRTC client should connect to one Isaac Sim instance at a time.
5. Do not downgrade ROS from Jazzy.
6. Prefer Tailscale IP over public IP for this workflow.
7. Do not mix browser/webviewer workflows with the native Isaac WebRTC Client unless intentionally testing an alternative client path.

---

## 21. References

- NVIDIA Isaac Sim Livestream Clients documentation: https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html
- Docker Compose build command: https://docs.docker.com/reference/cli/docker/compose/build/
- Docker Compose up command: https://docs.docker.com/reference/cli/docker/compose/up/
- Tailscale Linux installation documentation: https://tailscale.com/docs/install/linux
- ROS 2 Jazzy installation documentation: https://docs.ros.org/en/jazzy/Installation.html
- ROS 2 Jazzy Ubuntu packages documentation: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html

---

## 22. Final Expected State

After a successful setup and launch:

```text
Isaac Sim UI visible in Isaac Sim WebRTC Streaming Client
Brev Tailscale IP used as WebRTC server
TCP 49100 bidirectional over tailscale0
UDP 47998 bidirectional over tailscale0
NVENC encoder session active after client connection
ROS 2 Jazzy container running
Sionna container running
Full stack reproducible through scripts/netlab_brev_webrtc.sh
```
