# RRD analytics

Collect & store code metrics into [the Roud-Robin-Database](https://oss.oetiker.ch/rrdtool/)

# Prerequisites

### General

- You MUST configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

No special requirements for this UC

### Analytic UC

- You SHOULD configure a docker volume `api.pmccabe_collector.restapi.org.rrd_store` in order to preserve collected RRD files, because they represent analytics data and would be usefull for further analysis, thus it maybe adds up to make them persistent.

    `mkdir -p <local host RRD mount point> && chmod 777 <local host RRD mount point> && docker volume create -d local -o type=none -o device=<local host RRD mount point> -o o=bind api.pmccabe_collector.restapi.org.rrd_store`

# Build & Run image

### Analysis UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rrd_analytic:latest -f submodules/rrd/local/Dockerfile submodules/rrd/local`

Launching depends on [cyclomatic_complexity](../../cyclomatic_complexity), thereby launch the `pmccabe_cc` image at first.


`docker run -it --name rrd_analytic -v api.pmccabe_collector.restapi.org:/api --volumes-from main rrd_analytic:latest`


### Analytic UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rest_api:latest -f submodules/rrd/local/Dockerfile submodules/rrd/local`

Launching depends on [cyclomatic_complexity](../../cyclomatic_complexity), [observable_project_version_control](../../observable_project_version_control), thereby launch the `pmccabe_cc`, `project` images at first.

`docker run -it --name rrd_analytic -v api.pmccabe_collector.restapi.org:/api -v api.pmccabe_collector.restapi.org.rrd_store:/rrd_data --volumes-from main rrd_analytic:latest`
