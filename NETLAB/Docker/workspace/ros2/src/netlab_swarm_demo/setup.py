from setuptools import setup

package_name = "netlab_swarm_demo"

setup(
    name=package_name,
    version="9.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="NETLAB Research Platform",
    maintainer_email="netlab@example.com",
    description="NETLAB communication-gated SNaaS packet runtime for Isaac Sim, ROS 2 Jazzy, and Sionna.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "swarm_bridge = netlab_swarm_demo.swarm_bridge:main",
            "swarm_monitor = netlab_swarm_demo.swarm_monitor:main",
            "snaas_relay_chain = netlab_swarm_demo.snaas_relay_chain:main",
            "snaas_pretty_echo = netlab_swarm_demo.snaas_pretty_echo:main",
            "snaas_dashboard = netlab_swarm_demo.snaas_dashboard:main",
            "algorithm_bridge = netlab_swarm_demo.algorithm_bridge:main",
        ],
    },
)
