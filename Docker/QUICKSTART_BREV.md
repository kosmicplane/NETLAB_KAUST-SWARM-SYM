# Quickstart on NVIDIA Brev

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

## 4. Build

```bash
cd compose
cp .env.example .env
make build
```

## 5. Start Isaac Sim visualization service

```bash
make up-isaac
make logs-isaac
```

When Isaac finishes loading, connect with Isaac Sim WebRTC Streaming Client to the public IP of your Brev instance.

Required open ports:

```text
8210
49100
47998
```

## 6. Run visual validation scene

```bash
../scripts/run_isaac_sample_scene.sh
```

## 7. Start the rest of the stack

```bash
make up-ros2
make up-px4
make up-sionna
```

## 8. Stop everything

```bash
make down
```
