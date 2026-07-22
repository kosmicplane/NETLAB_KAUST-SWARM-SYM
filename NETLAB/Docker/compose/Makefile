COMPOSE=docker compose --env-file .env -f docker-compose.yml

prepare-brev:
	mkdir -p ../data/isaac/cache/main \
		../data/isaac/cache/computecache \
		../data/isaac/logs \
		../data/isaac/config \
		../data/isaac/local-data \
		../data/isaac/pkg \
		../workspace/shared \
		../workspace/results
	cp -f fastdds.xml ../workspace/shared/fastdds.xml

build:
	$(COMPOSE) build

build-isaac:
	$(COMPOSE) build isaac

build-ros2:
	$(COMPOSE) build ros2-core

build-sionna:
	$(COMPOSE) build sionna-engine

up: prepare-brev
	$(COMPOSE) up -d isaac ros2-core sionna-engine

up-isaac: prepare-brev
	$(COMPOSE) up -d isaac

up-ros2: prepare-brev
	$(COMPOSE) up -d ros2-core

up-sionna: prepare-brev
	$(COMPOSE) up -d sionna-engine

up-px4: prepare-brev
	$(COMPOSE) --profile px4 up -d px4

logs:
	$(COMPOSE) logs -f

logs-isaac:
	$(COMPOSE) logs -f isaac

ps:
	$(COMPOSE) ps

shell-isaac:
	docker exec -it isaac-sim bash

shell-ros2:
	docker exec -it netlab-ros2-core bash

shell-px4:
	docker exec -it px4-sitl bash

shell-sionna:
	docker exec -it netlab-sionna-engine bash

verify-ros2:
	docker exec -it netlab-ros2-core bash -lc 'source /opt/ros/jazzy/setup.bash && echo ROS_DISTRO=$$ROS_DISTRO && ros2 doctor --report | head -40'

verify-sionna:
	docker exec -it netlab-sionna-engine bash -lc 'python - <<"PY"\nimport sionna, tensorflow as tf\nprint("sionna", sionna.__version__)\nprint("tensorflow", tf.__version__)\nprint("gpus", tf.config.list_physical_devices("GPU"))\nPY'

down:
	$(COMPOSE) down

restart-isaac:
	$(COMPOSE) restart isaac
