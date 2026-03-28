This archive contains a starting multi-container layout for NetLab SWARM-SYM.

Included:
- docker/ros2/Dockerfile      -> ROS 2 Jazzy on Ubuntu 24.04
- docker/sionna/Dockerfile    -> Sionna + TensorFlow on CUDA Ubuntu 24.04
- docker/isaacsim/Dockerfile  -> Isaac Sim base image template
- docker/pegasus/Dockerfile   -> Pegasus on top of Isaac Sim runtime
- compose/docker-compose.yml  -> Service orchestration
- compose/.env.example        -> Example environment variables
- compose/Makefile            -> Simple helper commands

Important:
- Isaac Sim and Pegasus require NVIDIA GPU runtime.
- Isaac Sim base images may require NGC authentication and specific host setup.
- Pegasus is sensitive to Isaac Sim version compatibility.
