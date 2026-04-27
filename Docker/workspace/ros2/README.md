# ROS 2 workspace

Mount your ROS 2 packages here. Example structure:

```text
workspace/ros2/src/swarm_manager
workspace/ros2/src/sionna_bridge
workspace/ros2/src/fault_injection
workspace/ros2/src/experiment_logger
```

Build from the ROS 2 container:

```bash
cd /workspace/ros2
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
```
