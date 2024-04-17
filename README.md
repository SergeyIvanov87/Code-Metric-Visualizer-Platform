# pmccabe_visualizer_docker

The docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer

The service is supposed to monitor cyclomatic complexity of a C/C++ project.

The service implementation is still in progress and it has limited functionality.
The service is available as a `copilot`-based feature which has named `pmccabe_collector`. Only `pmccabe_collector` local-machine (Linux tested only) docker image is shipping at the moment.
The purpose of `pmccabe_collector` is to extend software developing experience by governing some code metric subset known as "cyclomatic complexity".
Launching `pmccabe_collector` and targeting it to your C/C++ project, you could leverage API populated by this service to collect, manifest and govern this metric subset.
All communication with the particular `pmccabe_collector` docker container is available either through simplest pseudo-filesystem API, which is populated in [API manifest](cyclomatic_complexity/API.fs), or using HTTP queries, if you decided to employ [REST API submodule](submodules/rest_api)
Whatever you prefered, the API subset remains the same. Thanks to the REST ideology, it is possible to generate both sets of API: requests could represent a particular hierarcy structure, thus `pmccabe_collector` leverages this idea and maps those API requests as a structure of nodes mapped to a filesystem hierarchy as directories and files inside the populated API-entry point `api.pmccabe_collector.restapi.org` resided in your project directory.
Each request can be executed as simple ACCESS-operation on a file named `exec` or `modify_this_file` in the bottom of relevant filesystem hierarchy in the same way as the Linux `/proc` pseudo-filesystem employed in order to read (and/or store) some system settings.

#### Few words about using the pseudo-filesystem API

The request

`GET api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph`

can be composed in the filesystem API mapped notation as the next transactional operation:

1) To initiate the request all you need is to send some data into the input PIPE `exec`:

`echo 0 > api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/exec`

which will establish IPC communication using pipes channel.

2) To extract a result of the operation just redirect read-request on the output PIPE `result.svg` into a destination file:

`cat api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET/result.svg > ~/my_flamegraph.svg`

Together these two operations represent the transaction. Although, contrary to acustomed transaction semantic, getting a result through reading the output PIPE will supplement you with the result of the last initiated request only. Therefore the API system doesn't act as a persistent queue. Although the operation pretends to be a synchronous "transaction", in reality it is not: you don't have to wait for a result using the output PIPE upon a request started, intead you can initiate a new operation by commiting write-request of the input `exec` PIPE. In this case the result of the former "transaction" would be discarded and the output PIPE would produce a new portion of data related to the last request you made.
This discrepancy to the traditional transactional semantic was settled deliberately.
Having non-blocking `exec` has been found more beneficial in this simple one-threading server case rather than preserving the pure synchronous transactions semantic.
Having a single-threaded server and the pure synchronous transaction, a client would have been blocked on next `exec`-request until they consumed request of the previous transaction through the ouput PIPE.
And schema "Send request/collect result" would transform into "Don't forget to collect the previous result/send request/collect result" which is said to be more complicated.

Thereby the following considerations are settled down for the current implementation:
a) A read-operation on the output PIPE **MUST** block until no requests are made.
b) A request initiation by using a write-operation on the `exec` node **MUST** be a non-blocking operation
c) A read-operation on the output PIPE MAY block temporary until the request execution is still in progress.

For more information about pseudo filesystem API usage and for changing the default request arguments please refer to the document [the cyclomatic complexity API manual](cyclomatic_complexity/README-CC-API-MANUAL.md)

If you prefer to use GUI rather than CLI, then you could just follow a path `api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET` in your favorite File Manager.
Opening the directory `../GET` triggers an inotify-event, and as soon as the request finishes you will find the result in a newly created file.
No any transactions in this case is meaning.
It is realy simple as it sounds! Regardless the approach you use (CLI or GUI).

The pseudo filesystem interface is only container API supported at the moment.


# Use-Cases (UCs)

There are few supported use-cases which are embodied by using different set of images in that repository:

### Analysis UC

To collect & check code metrics during your casual activities or making refactoring by demand using API.
To find more details, please check out for the [Analysis UC diagram](diagrams/analysis_UC.png)

### Analytic UC

Collect & store code metric in [Round-Robin-Database](https://oss.oetiker.ch/rrdtool) on a regular basis automatically.
To find more details, please check out for the [Analytic UC diagram](diagrams/analytic_UC.png)

# Prerequisites

### General

To be able to compose a use-case using docker images in this repo, the containers on a local host must communicate to each other.

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

Although `<local host mount point>` **SHOULD NOT** be employable by `Analytic UC`, you'd better create it.

- You **SHOULD** define environment variables `FLASK_RUN_HOST` and `FLASK_RUN_PORT` to determine where REST API service will listen incoming connections (default values `0.0.0.0` and `5000` respectfully).

### Analysis UC

You **MUST** define environment variable `PROJECT_PATH` when launching `docker compose  -f compose-analysis.yaml` (or use the following bind mount `--mount type=bind,src=${PROJECT_PATH}/,target=/mnt` for `docker run`), which **MUST** specify your source code project path.

### Analytic UC

You **MUST** define environment variables `PROJECT_URL` and `PROJECT_BRANCH` when launching both `docker compose  -f compose-analytic.yaml` and `docker build`, which specify your project repository and branch( `git` by default).
You **SHOULD** define the environment variable `CRON_REPO_UPDATE_SCHEDULE` to specify an analytic job invocation shedule (metrics collected every day, by default) in `crontab` format.

# HOW-TO

There are several ways to use these images: using `docker compose` to build and to launch all existing images or set them up using manual approach:

## To build & to Run entire services using Docker-Compose automatically (RECOMMENDED)

To leverage this fully-automated approach, please use `docker compose`:

### Analysis UC

`PROJECT_PATH=<path to your C/C++ repository> docker compose -f compose-analysis.yaml up`

which will build and launch the main image and all required submodules

### Analytic UC

`CRON_REPO_UPDATE_SCHEDULE="0 0 * * *" PROJECT_URL=https://github.com/<your repository> PROJECT_BRANCH=<your branch> docker compose -f compose-analytic.yaml up`

which will build and launch the all required services to carry out the conducting analysis

## To build & to Run each image separatedly

### Build & Run images

To build the images please follow up the corresponding section `Build & Run Image` in manuals below:

### Analysis UC

- [cyclomatic_complexity](cyclomatic_complexity/README.md)
- [rrd](submodules/rrd/README.md)
- [rest_api](submodules/rest_api/README.md)

### Analytic UC

- [observable_project_version_control](observable_project_version_control/README.md)
- [cyclomatic_complexity](cyclomatic_complexity/README.md)
- [rrd](submodules/rrd/README.md)
- [rest_api](submodules/rest_api/README.md)
- [service_broker](service_broker/README.md)


## To build & to Test entire services using Docker-Compose automatically (RECOMMENDED)

To leverage this fully-automated approach, please use `docker compose`:

### Analysis UC

`docker compose -f cyclomatic_complexity/compose-analysis.test.yaml build`

`docker compose -f cyclomatic_complexity/compose-analysis.test.yaml up --abort-on-container-exit`

which will build and test the main image and all required submodules

### Analytic UC

Coming soon...

## To build & to Test each image separatedly

### Build & Test images

To test the images please follow up the corresponding section `Testing the container` in manuals below:

### Analysis UC

- [cyclomatic_complexity](cyclomatic_complexity/README.md)
- [rrd](submodules/rrd/README.md)
- [rest_api](submodules/rest_api/README.md)

### Analytic UC

- [observable_project_version_control](observable_project_version_control/README.md)
- [cyclomatic_complexity](cyclomatic_complexity/README.md)
- [rrd](submodules/rrd/README.md)
- [rest_api](submodules/rest_api/README.md)
- [service_broker](service_broker/README.md)
