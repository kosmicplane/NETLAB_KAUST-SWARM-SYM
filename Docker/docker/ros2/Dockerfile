FROM ros:jazzy-ros-base-noble

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    ROS_DISTRO=jazzy \
    RMW_IMPLEMENTATION=rmw_fastrtps_cpp

COPY requirements/ros2-jazzy-apt.txt /tmp/ros2-jazzy-apt.txt
COPY requirements/ros2-python.txt /tmp/ros2-python.txt

RUN apt-get update && \
    grep -vE '^\s*(#|$)' /tmp/ros2-jazzy-apt.txt | xargs apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN rosdep init || true && rosdep update || true

RUN \
    python3 -m pip install --break-system-packages -r /tmp/ros2-python.txt

RUN echo 'source /opt/ros/jazzy/setup.bash' >> /root/.bashrc && \
    echo 'if [ -f /workspace/ros2/install/setup.bash ]; then source /workspace/ros2/install/setup.bash; fi' >> /root/.bashrc

WORKDIR /workspace/ros2
CMD ["/bin/bash"]
