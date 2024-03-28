# Cyclomatic Complexity

The service evaluates and manifest the cyclomatic complexity metric of code (C/C++ are supported yet) by implementing the [API](API)

# Prerequisites

### General

- You MUST configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`


### Analysis UC

You MUST define environment variable `PROJECT_PATH` when launching `docker compose  -f cyclomatic_complexity/compose-analysis.yaml` (or use the following bind mount `--mount type=bind,src=${PROJECT_PATH}/,target=/mnt` for `docker run`), which MUST specify your source code project path.

### Analytic UC

Since the service depends on [observable_project_version_control](../observable_project_version_control), no special requirements are expected: all necessary configuration will be exported automatically once the container started


# Build & Run image

### Analysis UC

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_cc:latest -f cyclomatic_complexity/Dockerfile .`

then launch it

`sudo docker run -it --mount type=bind,src=${PROJECT_PATH},target=/mnt -v api.pmccabe_collector.restapi.org:/api --name main pmccabe_vis:latest`

### Analytic UC

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_cc:latest -f cyclomatic_complexity/Dockerfile .`

Launching depends on [observable_project_version_control](../observable_project_version_control), thereby launch the `project` image at first.

`sudo docker run -it --name main --volumes-from project pmccabe_cc:latest`
