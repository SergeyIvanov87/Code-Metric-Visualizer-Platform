# RRD analytics

Collect & store code metrics into [the Roud-Robin-Database](https://oss.oetiker.ch/rrdtool/)

# Prerequisites

### General

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

No special requirements for this UC

### Analytic UC

- You **SHOULD** configure a docker volume `api.pmccabe_collector.rrd_analytic` in order to preserve collected RRD files, because they represent analytics data and would be usefull for further analysis, thus it maybe adds up to keep that persistent.

    `mkdir -p <local host RRD mount point> && chmod 777 <local host RRD mount point> && docker volume create -d local -o type=none -o device=<local host RRD mount point> -o o=bind api.pmccabe_collector.rrd_analytic`

# Build & Run image

### Analysis UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rrd_analytic:latest -f rrd/local/Dockerfile rrd/local`

Launching depends on [cyclomatic_complexity](../cyclomatic_complexity), thereby launch the `cc_visualizer` image at first.


`docker run -it --name rrd_analytic -v api.pmccabe_collector.restapi.org:/api --volumes-from cc_visualizer rrd_analytic:latest`


### Analytic UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rest_api:latest -f rrd/local/Dockerfile rrd/local`

Launching depends on [cyclomatic_complexity](../cyclomatic_complexity), [observable_project_version_control](../observable_project_version_control), thereby launch the `cc_visualizer`, `vcs_project` images at first.

`docker run -it --name rrd_analytic -v api.pmccabe_collector.restapi.org:/api -v api.pmccabe_collector.rrd_analytic:/rrd_data --volumes-from cc_visualizer rrd_analytic:latest`

# Testing the container

From the main repository directory run:

`docker compose -f rrd/compose-analysis.test.yaml build`

and then

`docker compose -f rrd/compose-analysis.test.yaml up --abort-on-container-exit`
