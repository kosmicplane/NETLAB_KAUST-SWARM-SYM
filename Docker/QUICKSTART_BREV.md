# Quickstart on NVIDIA Brev - ROS 2 Jazzy version

This version keeps the whole ROS-facing stack on ROS 2 Jazzy.

## 1. Connect to your Brev instance

```bash
brev shell <your-instance-name>
```

## 2. Copy this folder into the Brev workspace

Recommended location:

```bash
/home/ubuntu/workspace/kaust-netlab-swarm-sym-docker
```

## 3. Check GPU + Docker

```bash
cd /home/ubuntu/workspace/kaust-netlab-swarm-sym-docker
./scripts/check_brev_gpu.sh
```

Expected: `nvidia-smi` works on host and inside a CUDA Docker container.

## 4. Configure environment

```bash
cd compose
cp .env.example .env
nano .env
```

Set your Brev public IP:

```env
ISAACSIM_HOST=<YOUR_BREV_PUBLIC_IP>
```

Keep the ROS values as Jazzy:

```env
ROS_DISTRO=jazzy
ROS_DOMAIN_ID=42
RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

## 5. Prepare folders and build

```bash
make prepare-brev
make build
```

## 6. Start the main stack

This starts only the three main containers: Isaac Sim, ROS 2 Jazzy, and Sionna.

```bash
make up
make logs-isaac
```

When Isaac finishes loading, connect with the Isaac Sim WebRTC Streaming Client to the public IP of your Brev instance.

Required Brev ports:

```text
49100/tcp
47998/udp
```

Do not rely on port `8210` unless you add a separate web-viewer service.

## 7. Run visual validation scene

```bash
../scripts/run_isaac_sample_scene.sh
```

## 8. Verify ROS 2 Jazzy

```bash
make verify-ros2
```

Expected output includes:

```text
ROS_DISTRO=jazzy
```

## 9. Verify Sionna

```bash
make verify-sionna
```

## 10. Optional PX4 container

PX4 is now optional and behind a Docker Compose profile:

```bash
make up-px4
```

## 11. Stop everything

```bash
make down
```
