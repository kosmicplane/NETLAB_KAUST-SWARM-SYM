# ROS 2 Jazzy workspace

Mount your ROS 2 Jazzy packages here. Example structure:

```text
workspace/ros2/src/swarm_manager
workspace/ros2/src/sionna_bridge
workspace/ros2/src/fault_injection
workspace/ros2/src/experiment_logger
```

Build from the ROS 2 container:

```bash
cd /workspace/ros2
source /opt/ros/jazzy/setup.bash
colcon build
source install/setup.bash
```
