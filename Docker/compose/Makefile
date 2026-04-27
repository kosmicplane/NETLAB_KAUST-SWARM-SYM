COMPOSE=docker compose --env-file .env -f docker-compose.yml

build:
	$(COMPOSE) build

build-isaac:
	$(COMPOSE) build isaac

up:
	$(COMPOSE) up -d

up-isaac:
	$(COMPOSE) up -d isaac

up-ros2:
	$(COMPOSE) up -d ros2-core

up-px4:
	$(COMPOSE) up -d px4

up-sionna:
	$(COMPOSE) up -d sionna-engine

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

down:
	$(COMPOSE) down

restart-isaac:
	$(COMPOSE) restart isaac
