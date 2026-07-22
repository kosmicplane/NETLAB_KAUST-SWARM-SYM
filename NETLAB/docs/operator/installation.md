# Installation

For a destructive clean installation on Ubuntu/Brev:

```bash
cd "$HOME"
rm -rf NETLAB
unzip NETLAB.zip
cd NETLAB
chmod +x scripts/netlab scripts/*.sh Docker/workspace/ros2/*.sh Docker/scripts/*.sh
./scripts/bootstrap_host.sh --install-packages --non-interactive
```

The bootstrap creates `Docker/compose/.env`, validates all scenarios, repairs runtime directory modes, verifies Docker/GPU access, builds images, starts services in dependency order, synchronizes the reference scenario, and runs a live smoke test.
