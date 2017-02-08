.DEFAULT_GOAL := help
SHELL := /bin/bash

DEV_PATH := /usr/local/src

DCOSAR_PYLIB_LOCAL_PATH := $(CURDIR)
DCOSAR_PYLIB_CTR_MOUNT := /usr/local/src/adminrouter/

BRIDGE_DEVNAME := $(shell docker network inspect -f '{{ index .Options "com.docker.network.bridge.name" }}' bridge | awk 'NF')
BRIDGE_IP := $(shell ip a sh dev $(BRIDGE_DEVNAME) | awk '/inet / {print $$2}' | sed 's@/.*@@')

# FIXME: some problems with dns queries timing out, use hosts caching dns as a
# workaround for now
# DNS_DOCKER_OPTS := --dns=8.8.8.8 --dns=8.8.4.4
DNS_DOCKER_OPTS := --dns=$(BRIDGE_IP) --dns=8.8.8.8 --dns=8.8.4.4
DEVKIT_COMMON_DOCKER_OPTS := --name adminrouter-devkit \
	$(DNS_DOCKER_OPTS) \
	-e PYTHONDONTWRITEBYTECODE=true \
	-v $(DCOSAR_PYLIB_LOCAL_PATH):$(DCOSAR_PYLIB_CTR_MOUNT)

.PHONY: clean-devkit-container
clean-devkit-container:
	-docker rm -vf adminrouter-devkit > /dev/null 2>&1

.PHONY: clean-containers
clean-containers: clean-devkit-container

.PHONY: clean
clean:
	@echo "+ Cleaning up..."
	-sudo find . -type f -name '*.pyc' -delete

.PHONY: devkit
devkit:
	if $$(docker images | grep mesosphere/adminrouter-devkit | grep -q latest); then \
		echo "+ Devkit image already build"; \
	else \
		echo "+ Building devkit image"; \
		docker rmi -f mesosphere/adminrouter-devkit:latest; \
		docker build \
			--rm --force-rm \
			-t \
			mesosphere/adminrouter-devkit:latest ./docker/ ;\
	fi

.PHONY: update-devkit
update-devkit: clean-devkit-container
	docker build \
		--rm --force-rm \
		-t \
		mesosphere/adminrouter-devkit:latest ./docker/ ;\

.PHONY: shell
shell: clean-devkit-container devkit
	docker run --rm -it \
		$(DEVKIT_COMMON_DOCKER_OPTS) \
		--privileged \
		mesosphere/adminrouter-devkit:latest /bin/bash

.PHONY: test
test: clean-devkit-container devkit
	docker run \
		$(DEVKIT_COMMON_DOCKER_OPTS) \
		--privileged \
		mesosphere/adminrouter-devkit:latest /bin/bash -x -c " \
 			py.test \
 		"

.PHONY: flake8
flake8: clean-devkit-container devkit
	#FIXME - split it into two targets
	docker run \
		$(DEVKIT_COMMON_DOCKER_OPTS) \
		mesosphere/adminrouter-devkit:latest /bin/bash -x -c " \
			flake8 -v \
 		"

.PHONY: help
help:
	@echo "Please see README.md file."
