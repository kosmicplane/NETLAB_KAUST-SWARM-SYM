# NetLab SWARM-SYM
<img width="1536" height="1024" alt="logo" src="https://github.com/user-attachments/assets/d0294b35-5963-44eb-af9d-59d7d73b28c7" />


**NetLab SWARM-SYM** is a modular simulation platform for studying **UAV swarms as airborne communication infrastructure** in scenarios with limited, degraded, or unavailable terrestrial connectivity. The project is developed within the **Networking Research Lab (NetLab)** and is centered on the ideas of **Drone-as-a-Service (DaaS)** and **Swarm Network-as-a-Service (SNaaS)**, where coordinated drones can provide temporary connectivity, signal amplification, data transmission, and communication backup under demanding or disrupted conditions.

---

## Problem Statement

Modern communication systems are vulnerable to infrastructure damage, coverage gaps, overloaded networks, and low-connectivity environments. In disaster scenarios, remote areas, or large-scale events, terrestrial communication infrastructure may become partially unavailable, saturated, or completely inoperative.

This project addresses the problem of how to use **coordinated UAV swarms** as a flexible airborne communication layer capable of supporting or restoring service in these situations. The challenge is not only to simulate drone motion, but also to model:

- communication coverage and signal quality,
- multi-agent coordination,
- autonomy under telecom constraints,
- failure scenarios,
- and service continuity under dynamic conditions.

The broader research problem is aligned with the DaaS vision of drones as modular service providers and with the SNaaS concept of swarm-based connectivity driven by QoS/SLA requirements such as latency, throughput, and stability.

---

## Project Objective

The main objective of this project is to develop a **high-fidelity, well-documented, and fully replicable simulation environment** capable of modeling:

- drone swarms,
- their operating conditions,
- control and autonomy modules,
- telecom-aware behavior,
- and fault or disruption scenarios.

This platform is intended to serve as a **reliable testbed for real-time data generation, collection, processing, and validation**.

Its primary research focus is **Drones-as-a-Service (DaaS)**, with particular emphasis on evaluating the feasibility of drones as airborne platforms for:

- signal amplification,
- data transmission,
- communication relay,
- and emergency backup in the event of failures in telecommunication systems.

As secondary objectives, the platform should also support use cases such as:

- partial or total damage to urban communication infrastructure,
- SNaaS deployment in densely populated areas with saturated drone traffic during large-scale events,
- and real-time data transmission applications such as remote camel monitoring.

---

## Research Background

This repository is motivated by recent research directions in:

### Drone-as-a-Service (DaaS)
DaaS frames drones as service-oriented resources that can be abstracted, orchestrated, and delivered on demand. The DaaS perspective highlights key issues such as:

- scalable service architectures,
- cloud/edge integration,
- energy-aware decision-making,
- communication and data management,
- weather-aware autonomy,
- cybersecurity,
- and swarm coordination.

### Swarm Network-as-a-Service (SNaaS)
SNaaS extends this idea by treating UAV swarms as providers of on-demand connectivity services. In this view, drone-to-drone and drone-to-device interactions can be composed according to QoS/SLA goals such as:

- latency,
- throughput,
- stability,
- and adaptability under load.

These ideas are especially relevant for communication-aware autonomy, resilient reconfiguration, and adaptive swarm control under telecom constraints.

---

## Why This Project Matters

The project explores how drone swarms can move beyond sensing-only roles and become **active communication infrastructure**. This is especially relevant for:

- underserved or remote regions,
- emergency and disaster response,
- infrastructure failure recovery,
- temporary event-based network support,
- and adaptive service provisioning under uncertainty.

The intended contribution is not only a single simulation demo, but a reusable and extensible research platform for future experiments in airborne connectivity.

---

## Core Requirements of the Simulation Platform

To properly simulate the project, the platform must provide:

1. realistic drone physics, including flight dynamics, aerodynamics, and energy consumption,
2. high-fidelity environments with urban structures, terrain, obstacles, and weather,
3. multi-agent simulation for simultaneous drone coordination,
4. telecommunications and data transmission modeling, including coverage, propagation, interference, latency, and throughput,
5. support for optimization, AI, and external processing modules,
6. control system simulation, including PID, autopilot, manual operation, and autonomy,
7. natural hazard and disaster simulation,
8. fault injection and operational failure modeling,
9. scalability for larger urban or rural environments,
10. integration with external frameworks such as ROS 2 and telecom analysis tools,
11. real-time monitoring and visualization,
12. reproducibility through configurable scenarios,
13. sensor simulation such as GPS, IMU, cameras, LiDAR, and communication payloads,
14. energy and resource modeling,
15. and event-driven simulation for demand spikes or emergency situations.

---

## Selected Technology Stack

According to the current project assessment, the tentative stack is based on:

- **ROS 2** for middleware, messaging, node orchestration, and distributed system integration,
- **Isaac Sim** for high-fidelity simulation environments, rendering, sensors, and physics,
- **Pegasus Simulator** for realistic multirotor/UAV simulation on top of Isaac Sim,
- **Sionna** for telecom and coverage modeling, including radio maps, propagation, RSS/SINR estimation, and coverage analysis,
- **Docker / Docker Compose** for modular, reproducible, and scalable deployment,
- optional autopilot/control interfaces such as **PX4**, **QGroundControl**, or related adapters depending on the experiment setup.

This stack was selected because it offers the most technically powerful combination when the priority is **maximum realism in UAV/swarm behavior, environment fidelity, and telecom-aware experimentation**, even though it increases integration complexity.

---

## System Requirements

This project targets a high-fidelity UAV swarm simulation stack based on **Isaac Sim, Pegasus Simulator, ROS 2, and Sionna**, so it should be deployed on a **Linux workstation with strong GPU support** rather than a standard laptop. The selected combination was identified as the most technically powerful option for maximizing UAV realism, telecom realism, and experimental scalability. :contentReference[oaicite:13]{index=13}

### Recommended environment

- **OS:** Ubuntu 24.04
- **CPU:** Intel Core i7 / Ryzen 7 or better
- **RAM:** 16 GB recommended
- **GPU:** NVIDIA RTX-class GPU
- **VRAM:** 8 GB minimum
- **Storage:** 100 GB SSD
- **Containerization:** Docker and Docker Compose
- **Notes:** Isaac Sim containers are Linux-only; Pegasus inherits Isaac Sim requirements; Sionna is recommended on Ubuntu 24.04 and typically benefits from TensorFlow-compatible GPU support. 

## What Each Tool Contributes

### ROS 2
ROS 2 acts as the backbone of the platform. It manages:
- communication between modules,
- state and command topics,
- telemetry,
- planner/controller integration,
- and distributed execution across components.

### Isaac Sim
Isaac Sim provides:
- high-fidelity 3D environments,
- realistic visual and physical simulation,
- sensor integration,
- and urban/structured scenarios suitable for UAV testing.

### Pegasus Simulator
Pegasus adds:
- multirotor modeling,
- UAV dynamics and control support,
- localization and telemetry interfaces,
- and more natural swarm-oriented UAV experimentation on top of Isaac Sim.

### Sionna
Sionna is responsible for:
- telecom and coverage analysis,
- channel and propagation modeling,
- radio map estimation,
- RSS/SINR analysis,
- and communication-aware feedback for decision-making.

### Docker
Docker ensures:
- reproducible environments,
- easier multi-machine deployment,
- modular service separation,
- and cleaner experiment orchestration.

---

## Project Description

NetLab SWARM-SYM is not intended as a single-purpose simulator, but as a **modular research platform** for experiments involving:

- airborne telecom service provision,
- multi-UAV coordination,
- communication-aware autonomy,
- resilience under failures,
- and scalable simulation workflows.

The project aims to support iterative research, from single-UAV validation to multi-agent telecom-aware missions, and eventually to more advanced experiments involving fault tolerance, adaptive repositioning, and service optimization.

---

## High-Level Architecture

The platform is structured around three main technical layers:

### 1. Simulation Layer
This layer contains the high-fidelity environment and UAV simulation:
- Isaac Sim environments,
- Pegasus simulation engine,
- drone dynamics,
- localization,
- and simulated sensor outputs.

### 2. Middleware and Coordination Layer
This layer is centered on ROS 2 and handles:
- mission management,
- swarm coordination,
- telemetry exchange,
- bridge nodes,
- command distribution,
- and integration between simulation and telecom modules.

### 3. Telecom and Control Layer
This layer contains the Sionna-based communication modules:
- channel/propagation analysis,
- radio map generation,
- coverage estimation,
- RSS/SINR evaluation,
- and telecom-aware optimization.

### 4. Monitoring and Data Layer
This layer supports:
- logging,
- rosbags,
- metrics databases,
- result exporting,
- and experiment reproducibility.

---

## Repository Structure

A suggested repository structure for this project is:

```bash
NetLab-SWARM-SYM/
├── README.md
├── docs/
│   ├── problem_statement/
│   ├── architecture/
│   ├── references/
│   └── experiment_notes/
├── docker/
│   ├── isaac/
│   ├── ros2/
│   ├── sionna/
│   └── compose/
├── configs/
│   ├── simulation/
│   ├── swarm/
│   ├── telecom/
│   └── missions/
├── src/
│   ├── mission_manager/
│   ├── swarm_coordination/
│   ├── telemetry_bridge/
│   ├── coverage_engine/
│   ├── control_adapters/
│   └── monitoring/
├── scenarios/
│   ├── urban/
│   ├── disaster/
│   ├── remote_area/
│   └── event_driven/
├── scripts/
│   ├── setup/
│   ├── run/
│   ├── validation/
│   └── analysis/
├── data/
│   ├── logs/
│   ├── rosbags/
│   ├── metrics/
│   └── outputs/
└── assets/
    ├── maps/
    ├── models/
    └── media/
```

### Setup Instructions

This section is divided into two setup paths:

- **Local users**: for users who only want to clone and run the repository on their local machine.
- **Collaborators**: for users who will also contribute code and push changes to the remote repository.

> **Assumption:** Git is already installed on the system.

---

## 👤 1. Local Users

### 1.1 Clone the repository

```bash
git clone https://github.com/kosmicplane/NETLAB_KAUST-SWARM-SYM
cd NETLAB_KAUST-SWARM-SYM
```

### 1.2 Install Docker Engine and Docker Compose

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 1.3 Allow Docker to run without `sudo`

```bash
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker
```

### 1.4 Verify Docker installation

```bash
docker --version
docker compose version
docker run hello-world
```

### 1.5 Install Tilix and tmux

```bash
sudo apt update
sudo apt install -y tilix tmux
```

### 1.6 Verify Tilix and tmux installation

```bash
tilix --version
tmux -V
```

---

## 🤝 2. Collaborators

Collaborators must complete all the steps in the **Local Users** section first. After that, they must configure GitHub SSH access on the new machine.

### 2.1 Generate an SSH key

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

When prompted for the file location, press `Enter` to use the default path:

```bash
~/.ssh/id_ed25519
```

### 2.2 Start the SSH agent and add the key

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 2.3 Copy the public key

```bash
cat ~/.ssh/id_ed25519.pub
```

Copy the full output.

### 2.4 Add the SSH key to GitHub

Go to:

**GitHub → Settings → SSH and GPG keys → New SSH key**

Then:

- set a title for the machine, for example: `ubuntu-workstation`
- paste the public key
- save the key

### 2.5 Test the SSH connection

```bash
ssh -T git@github.com
```

If prompted, type:

```bash
yes
```

If the configuration is correct, GitHub will confirm that the authentication was successful.

### 2.6 Configure Git identity on the new machine

```bash
git config --global user.name "Your Name"
git config --global user.email "your_email@example.com"
```

Optional but recommended:

```bash
git config --global init.defaultBranch main
git config --global pull.rebase false
```

### 2.7 Ensure the repository remote uses SSH

Check the current remote:

```bash
git remote -v
```

If it is using HTTPS, change it to SSH:

```bash
git remote set-url origin git@github.com:kosmicplane/NETLAB_KAUST-SWARM-SYM.git
```

Verify again:

```bash
git remote -v
```

### 2.8 Pull the latest changes

```bash
git pull origin main
```

At this point, the new machine is ready to contribute to the repository.

---

## 📝 Notes

- These instructions are intended for **Ubuntu-based systems**.
- Docker is installed from Docker’s official Ubuntu repository.
- Docker Compose is installed as the official Docker CLI plugin.
- If Docker still requires `sudo` after setup, log out and log back in, or restart the machine.
- Do **not** use `sudo` with Git commands inside the repository, as this may cause file permission issues.
