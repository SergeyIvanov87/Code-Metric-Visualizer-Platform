# Service Broker

The service is an orchestrator, which holds a control logic of the Analytic UC

# Prerequisites

### General

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

The service is not engaged into this UC

### Analytic UC

No special configuration required

# Build & Run image

### Analysis UC

The service is not engaged into this UC

### Analytic UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t service_broker:latest -f service_broker/Dockerfile .`

The service requires all other services to be started. Once they started, use the following command:

`docker run -it --name broker --volumes-from vcs_project -e CRON_REPO_UPDATE_SCHEDULE="0 0 * * *" service_broker:latest`
