# Two-Drone Hover Demonstration: Isaac Sim, ROS 2 Jazzy, and Sionna

## Purpose

This demonstration validates the first end-to-end communication loop required by the NETLAB KAUST SWARM-SYM simulator. It loads two UAV-like visual drones into Isaac Sim, animates both drones in a hover state, publishes their real-time states into ROS 2 Jazzy, queries a Sionna-side link service for radio-link metrics, and relays a telemetry message from Drone 1 to Drone 2 through ROS 2.

The demo is intentionally lightweight. It is not a full PX4/Pegasus controller or a full Sionna RT scene yet. Its purpose is to prove that the three runtime layers are connected:

1. **Isaac Sim** provides the visual/kinematic scene and live drone pose publishing.
2. **ROS 2 Jazzy** acts as the real-time middleware and message relay layer.
3. **Sionna** provides link-quality computation through a service running in the Sionna container.

## Files added

```text
Docker/workspace/isaac/scripts/two_drone_hover_live.py
Docker/workspace/ros2/src/netlab_swarm_demo/package.xml
Docker/workspace/ros2/src/netlab_swarm_demo/setup.py
Docker/workspace/ros2/src/netlab_swarm_demo/setup.cfg
Docker/workspace/ros2/src/netlab_swarm_demo/resource/netlab_swarm_demo
Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/__init__.py
Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/swarm_bridge.py
Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/swarm_monitor.py
Docker/workspace/sionna/realtime_link_server.py
scripts/netlab_swarm_demo.sh
Docs/two_drone_hover_sionna_ros_demo.md
```

## Runtime architecture

```text
Isaac Sim WebRTC UI
    |
    |  two_drone_hover_live.py
    |  publishes /swarm/drone_1/state and /swarm/drone_2/state
    v
ROS 2 Jazzy container
    |
    |  netlab_swarm_demo swarm_bridge
    |  queries Sionna using HTTP POST /link
    v
Sionna container
    |
    |  realtime_link_server.py
    |  returns distance, path loss, SNR, capacity, delay, status
    v
ROS 2 Jazzy container
    |
    |  publishes /swarm/sionna/link_metrics
    |  publishes /swarm/drone_2/inbox
    v
Isaac Sim live script
    |
    |  subscribes to /swarm/sionna/link_metrics and /swarm/drone_2/inbox
    |  updates visual link color and status lights
```

## Main ROS topics

| Topic | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `/swarm/drone_1/state` | `geometry_msgs/msg/PoseStamped` | Isaac Sim | ROS bridge | Drone 1 real-time position |
| `/swarm/drone_2/state` | `geometry_msgs/msg/PoseStamped` | Isaac Sim | ROS bridge | Drone 2 real-time position |
| `/swarm/drone_1/telemetry` | `std_msgs/msg/String` | Isaac Sim | ROS tools | Drone 1 JSON telemetry |
| `/swarm/drone_2/telemetry` | `std_msgs/msg/String` | Isaac Sim | ROS tools | Drone 2 JSON telemetry |
| `/swarm/sionna/link_metrics` | `std_msgs/msg/String` | ROS bridge | Isaac Sim / monitor | JSON Sionna link metrics |
| `/swarm/drone_1/outbox` | `std_msgs/msg/String` | ROS bridge | ROS tools | Drone 1 outgoing message |
| `/swarm/drone_2/inbox` | `std_msgs/msg/String` | ROS bridge / Isaac subscriber | Isaac Sim / ROS tools | Message delivered to Drone 2 |
| `/swarm/drone_2/ack` | `std_msgs/msg/String` | ROS bridge | ROS tools | Drone 2 acknowledgement |

## Starting the demo

The base stack must already be running with Isaac, ROS 2, and Sionna containers:

```bash
cd ~/workspace/NETLAB
./scripts/netlab_brev_webrtc.sh start-stack
```

Then start the two-drone demo backend:

```bash
cd ~/workspace/NETLAB
chmod +x scripts/netlab_swarm_demo.sh
./scripts/netlab_swarm_demo.sh start
```

This command performs three actions:

1. Starts the Sionna real-time link HTTP service inside the Sionna container.
2. Builds the ROS 2 package `netlab_swarm_demo` inside the ROS 2 Jazzy workspace.
3. Starts the ROS 2 bridge node that connects Isaac drone poses to Sionna link metrics and inter-drone telemetry.

After the backend is running, open the streamed Isaac Sim UI and run this inside **Window -> Script Editor**:

```python
exec(open("/workspace/isaac/scripts/two_drone_hover_live.py").read())
```

Expected visual result:

- Two quadrotor-style drones appear in the scene.
- Both drones hover at approximately constant altitude with a small oscillation.
- A visual link line connects Drone 1 and Drone 2.
- The link and status lights change color according to the latest Sionna link status.

## Monitoring the demo

Show useful monitoring commands:

```bash
./scripts/netlab_swarm_demo.sh monitor
```

Run the compact ROS monitor:

```bash
docker exec -it netlab-ros2-core bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 run netlab_swarm_demo swarm_monitor'
```

Echo Sionna metrics directly:

```bash
docker exec -it netlab-ros2-core bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/sionna/link_metrics'
```

Echo Drone 2 inbox:

```bash
docker exec -it netlab-ros2-core bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/drone_2/inbox'
```

Check Sionna service health:

```bash
curl -s http://127.0.0.1:8090/health
```

Run a full demo doctor:

```bash
./scripts/netlab_swarm_demo.sh doctor
```

## Stopping the demo

Stop ROS and Sionna demo processes:

```bash
./scripts/netlab_swarm_demo.sh stop
```

The Isaac visual script runs inside the live Isaac Sim session. To reset it, reload the stage or restart the Isaac container.

## Current limitations

This demonstration is an integration proof, not the final autonomy stack.

- The drone hover is kinematic, not a full PX4/Pegasus controller loop.
- The Sionna service currently computes deterministic link metrics from drone geometry and imports Sionna inside the Sionna container to verify that the Sionna runtime is present.
- Full Sionna RT ray tracing over USD-derived scene geometry is left for the next development phase.
- Standard ROS 2 messages are used intentionally to avoid custom message generation during the first integration test.

## Success criteria

The task is considered successful when all of the following are true:

1. Isaac Sim shows two drones hovering.
2. ROS 2 lists `/swarm/drone_1/state` and `/swarm/drone_2/state`.
3. Sionna health endpoint returns `ok: true`.
4. ROS 2 publishes `/swarm/sionna/link_metrics` with changing link metrics.
5. ROS 2 publishes `/swarm/drone_2/inbox`, proving that Drone 1 information is relayed to Drone 2.
6. The visual drone link in Isaac changes color according to the latest Sionna status.
