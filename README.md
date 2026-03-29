# NetLab SWARM-SYM

<p align="center">
  <img src="https://github.com/user-attachments/assets/d0294b35-5963-44eb-af9d-59d7d73b28c7" alt="NetLab SWARM-SYM logo" width="900"/>
</p>

<p align="center">
  <strong>High-Fidelity Simulation Platform for UAV Swarms as Airborne Communication Infrastructure</strong>
</p>

<p align="center">
  Developed within the <strong>Networking Research Lab (NetLab)</strong>
</p>

---

## Overview

NetLab SWARM-SYM is a research-oriented simulation platform dedicated to the modeling, evaluation, and validation of UAV swarms as airborne communication infrastructure. The project addresses operational scenarios in which terrestrial communication systems are unavailable, degraded, overloaded, or insufficient, and investigates how coordinated multi-UAV systems can provide adaptive, resilient, and on-demand connectivity services.

The project is grounded in the paradigms of **Drone-as-a-Service (DaaS)** and **Swarm Network-as-a-Service (SNaaS)**. Within this framework, UAVs are not treated merely as mobile sensing platforms, but as active networked assets capable of supporting communication relay, temporary coverage extension, signal reinforcement, and emergency telecommunications recovery.

This repository aims to provide a **reproducible, extensible, and high-fidelity simulation environment** in which airborne communication strategies can be studied under realistic environmental, operational, and failure conditions. In doing so, the project supports rigorous experimentation in telecom-aware autonomy, swarm coordination, service continuity, and fault-tolerant aerial networking.

---

## Research Scope

The primary research direction of this repository is the study of **Drones-as-a-Service (DaaS)** for telecommunications-oriented applications, particularly those involving:

- airborne signal amplification,
- communication relay and data forwarding,
- temporary connectivity provisioning,
- infrastructure support during outages,
- and emergency communication restoration.

A complementary research axis is **Swarm Network-as-a-Service (SNaaS)**, in which coordinated UAV swarms are modeled as on-demand providers of communication services operating under **QoS/SLA-driven objectives**, including:

- latency,
- throughput,
- stability,
- adaptability,
- and resilience under dynamic demand or infrastructure failure.

---

## Objectives

### Main Objective

Develop a **high-fidelity, modular, and fully replicable simulation environment** capable of modeling:

- UAV swarms,
- operational conditions,
- control systems,
- telecom-aware decision-making,
- and fault or disruption scenarios.

This environment is intended to function as a **reliable experimental testbed** for data generation, experiment validation, and reproducible evaluation of airborne communication strategies.

### Secondary Objectives

The platform is also intended to support representative scenarios such as:

- communication recovery in disaster-affected areas,
- temporary connectivity deployment in dense or overloaded environments,
- infrastructure substitution in remote or underserved regions,
- and real-time monitoring applications in low-connectivity settings.

---

## Motivation

Contemporary communication infrastructure remains vulnerable to overload, service degradation, partial failure, and environmental disruption. These limitations become particularly critical in natural disasters, large-scale temporary events, remote-area operations, and infrastructure outage scenarios.

This project investigates how **multi-UAV systems** can operate as a **flexible airborne communication layer**, capable of restoring, extending, or reinforcing network services when conventional ground infrastructure is unavailable or insufficient. The scope of the project therefore extends beyond aerial mobility alone and includes the integrated simulation of:

- UAV behavior and coordination,
- telecom-aware autonomy,
- communication coverage and quality,
- service continuity,
- and fault tolerance.

---

## Core Requirements

To support the intended research goals, the simulation platform must provide:

1. realistic drone physics, including aerodynamics and energy consumption,
2. high-fidelity environments with terrain, buildings, and obstacles,
3. multi-agent UAV simulation,
4. telecommunications modeling, including propagation, interference, RSS, SINR, latency, and throughput,
5. support for AI, optimization, and external analytics modules,
6. control simulation with autopilot and autonomy integration,
7. hazard and disruption scenario modeling,
8. fault injection and failure analysis,
9. scalability across urban and rural environments,
10. interoperability with external frameworks such as ROS 2 and telecom engines,
11. real-time monitoring and visualization,
12. experiment reproducibility through configurable scenarios,
13. sensor simulation such as GPS, IMU, LiDAR, and cameras,
14. onboard resource and energy modeling,
15. and event-driven simulation for emergency or demand-spike conditions.

---

## Technology Stack

The current proposed stack is composed of the following technologies:

- **[ROS 2](https://github.com/ros2/ros2)** for middleware, orchestration, and distributed communication,
- **Isaac Sim** for high-fidelity physics, rendering, and sensor simulation,
- **[Pegasus Simulator](https://github.com/PegasusSimulator/PegasusSimulator)** for realistic UAV and multirotor simulation on top of Isaac Sim,
- **[Sionna](https://github.com/NVlabs/sionna)** for telecom, radio propagation, and coverage modeling,
- **Docker / Docker Compose** for reproducibility and modular deployment,
- and optional autopilot and mission interfaces such as **[PX4-Autopilot](https://github.com/PX4/PX4-Autopilot)** and **[QGroundControl](https://github.com/mavlink/qgroundcontrol)**.

This stack was selected because it offers an effective balance between:

- UAV realism,
- environment fidelity,
- telecom-aware experimentation,
- and scalable research workflows.

---

## System Requirements

This project targets a Linux-based high-fidelity simulation workstation with strong GPU support.

### Recommended Environment

- **Operating System:** Ubuntu 24.04
- **Processor:** Intel Core i7 / AMD Ryzen 7 or better
- **Memory:** 16 GB RAM minimum recommended
- **Graphics:** NVIDIA RTX-class GPU
- **Video Memory:** 8 GB VRAM minimum
- **Storage:** 100 GB SSD or more
- **Containerization:** Docker and Docker Compose

> **Note:** Isaac Sim and Pegasus-based workflows benefit substantially from systems with strong NVIDIA GPU support.

---

## High-Level Architecture

The platform is organized into four technical layers.

### 1. Simulation Layer

Responsible for the physical and visual simulation environment:

- Isaac Sim environments,
- Pegasus simulation engine,
- UAV dynamics,
- localization,
- and simulated sensors.

### 2. Middleware and Coordination Layer

Centered on ROS 2 for distributed integration:

- mission management,
- swarm coordination,
- telemetry exchange,
- bridge nodes,
- command distribution,
- and module integration.

### 3. Telecom and Control Layer

Responsible for communication-aware analysis and feedback:

- radio map generation,
- propagation modeling,
- coverage estimation,
- RSS / SINR evaluation,
- and telecom-aware optimization.

### 4. Monitoring and Data Layer

Supports experiment traceability and reproducibility through:

- logging,
- rosbags,
- metrics storage,
- exported results,
- and experiment records.

---

## Repository Structure

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

## Docker Compose Validation Steps

After creating or modifying any Dockerfile or Compose configuration, validate the services step by step instead of building the entire stack at once.

### 1. Move to the Compose directory

```bash
cd Docker/compose
```

### 2. Validate the Compose configuration

This checks whether the `docker-compose.yml` file is valid and whether all referenced services are correctly defined.

```bash
docker compose config
```

### 3. Build the services individually

Build each service separately to identify errors more easily.

```bash
docker compose build ros2-core
docker compose build sionna-engine
docker compose build isaacsim
docker compose build pegasus
```

### 4. Rebuild without cache if needed

If a service still fails after modifying its Dockerfile, rebuild it without using cached layers.

```bash
docker compose build --no-cache ros2-core
docker compose build --no-cache sionna-engine
docker compose build --no-cache isaacsim
docker compose build --no-cache pegasus
```

### 5. Start only the validated services

Once a service builds successfully, it can be started independently for testing.

```bash
docker compose up ros2-core
docker compose up sionna-engine
```

To run them in the background:

```bash
docker compose up -d ros2-core sionna-engine
```

### 6. Check container status

```bash
docker compose ps
```

### 7. Inspect logs

Logs should be reviewed after bringing up a service to confirm that it started correctly.

```bash
docker compose logs ros2-core
docker compose logs sionna-engine
docker compose logs isaacsim
docker compose logs pegasus
```

### 8. Shut down the stack

```bash
docker compose down
```

To also remove associated volumes:

```bash
docker compose down -v
```

---

## Recommended Validation Order

For this project, the recommended validation order is:

1. `ros2-core`
2. `sionna-engine`
3. `isaacsim`
4. `pegasus`

This order helps isolate dependency or runtime issues progressively, starting from the lighter services and moving toward the more GPU- and simulation-dependent components.

---

## Notes

- If Docker is configured for non-root usage, `sudo` is not required.
- If Docker still requires elevated permissions on your machine, prepend `sudo` to the commands above.
- It is recommended to validate each service independently before attempting:

```bash
docker compose up --build
```

which builds and launches the full multicontainer stack.
