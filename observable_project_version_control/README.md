# Observable Project Version Control

The service owns a local copy of a monitored project, carries out the Versioning Control operations populated by [API](API) and populates this local copy directory as `VOLUME` for other containers

# Prerequisites

### General

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

The service is not engaged into this UC

### Analytic UC

You **MUST** define environment variables `PROJECT_URL` and `PROJECT_BRANCH` when launching both `docker compose  -f compose-analytic.yaml` and `docker build`, which specify your project repository and branch( `git` by default).

# Build & Run image

### Analysis UC

The service is not engaged into this UC

### Analytic UC

From the main repository directory run:

`docker build -t vcs-project:latest -f observable_project_version_control/Dockerfile .`

`docker run -it --name vcs-project -v api.pmccabe_collector.restapi.org:/api -e PROJECT_URL=<your project repository> -e PROJECT_BRANCH=<your project branch> vcs-project:latest`
