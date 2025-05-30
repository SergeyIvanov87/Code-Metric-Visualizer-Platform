# Cyclomatic Complexity

The service evaluates and manifests the cyclomatic complexity metric of code (C/C++ are supported yet) by implementing the [API](API)

# Prerequisites

### General

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `LOCAL_HOST_MOUNT_POINT=<local host mount point> && mkdir -p ${LOCAL_HOST_MOUNT_POINT} && chmod 777 ${LOCAL_HOST_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${LOCAL_HOST_MOUNT_POINT} -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

You **MUST** define environment variable `PROJECT_PATH` when launching `docker compose  -f cyclomatic_complexity/compose-analysis.yaml` (or use the following bind mount `--mount type=bind,src=${PROJECT_PATH}/,target=/mnt` for `docker run`), which **MUST** specify your source code project path.

### Analytic UC

Since the service depends on [observable_project_version_control](../observable_project_version_control), no special requirements are expected: all necessary configuration will be exported automatically once the container started


# Build & Run image

### Analysis UC

From the main repository directory run:

`docker build -t cc_visualizer:latest -f cyclomatic_complexity/Dockerfile .`

then launch it

`docker run -it --mount type=bind,src=${PROJECT_PATH},target=/mnt -v api.pmccabe_collector.restapi.org:/api --name cc_visualizer cc_visualizer:latest`

### Analytic UC

From the main repository directory run:

`docker build -t cc_visualizer:latest -f cyclomatic_complexity/Dockerfile .`

Launching depends on [observable_project_version_control](../observable_project_version_control), thereby launch the `vcs_project` image at first.

`docker run -it --name cc_visualizer --volumes-from vcs_project cc_visualizer:latest`

# Testing the container

### Standalone container functional test

From the main repository directory run:

`docker compose -f cyclomatic_complexity/compose-functional.test.yaml build`

and then

`docker compose -f cyclomatic_complexity/compose-functional.test.yaml up --abort-on-container-exit`

### All containers functional tests

`docker compose -f compose-functional.test.yaml up --abort-on-container-exit`
