# pmccabe_visualizer_docker

The docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer

The service is supposed to monitor cyclomatic complexity of a C/C++ project.

The service implementation is still in progress and it has limited functionality.
The service is available as a `copilot`-based feature which has named `pmccabe_collector`. Only `pmccabe_collector` local-machine (Linux tested only) docker image is shipping at the moment.
The purpose of `pmccabe_collector` is to reach a similar functionality as it enhanced by the `sidecar` pattern which goal here is to extend software developing experience by governing some code metric subset known as "cyclomatic complexity".
Launching `pmccabe_collector` and binding a docker shared folder into your existing C/C++ project directory, allow this container to populate filesystem API entrypoints, which are served for collecting and populating this metric subset.
All communication with the `pmccabe_collector` docker service is available through pseudo-filesystem API, which is populated in [API manifest](cyclomatic_complexity/API.fs)

According to the REST ideology, requests could represent a particular hierarcy structure, thus `pmccabe_collector` leverages this idea and maps those API requests as a structure of nodes mapped to a filesystem hierarchy as directories and files inside the populated API-entry point `api.pmccabe_collector.restapi.org` resided in your project directory.
Each request can be executed as simple ACCESS-operation on a file named `exec` or `modify_this_file` in the bottom of relevant filesystem hierarchy in the same way as the Linux `/proc` pseudo-filesystem employed in order to read (and/or store) some system settings.

#### For example:

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
a) A read-operation on the output PIPE MUST block until no requests are made.
b) A request initiation by using a write-operation on the `exec` node MUST be a non-blocking operation
c) A read-operation on the output PIPE MAY block temporary until the request execution is still in progress.

For more information about pseudo filesystem API usage and for changing the default request arguments please refer to the document [the cyclomatic complexity API manual](cyclomatic_complexity/README-CC-API-MANUAL.md)

If you prefer to use GUI rather than CLI, then just open a path `api.pmccabe_collector.restapi.org/cc/statistic/view/flamegraph/GET` in your favorite File Manager.
Opening the directory `../GET` triggers an inotify-event, and as soon as the request finishes you will find the result in a newly created file.
No any transactions in this case is meaning.
It is realy simple as it sounds! Regardless the approach you use (CLI or GUI).

The pseudo filesystem interface is only container API supported at the moment.

# HOW-TO

There are several ways to use these images: using `docker-compose` to build and launch all existing images or set them up using manual approach:

## To build & Run Images using Docker-Compose automatically

To leverage this fully-automated approach, please use `docker-compose`:

`PROJECT_PATH=<path to your C/C++ repository> docker compose up`

which will build and launch the main image and all registered submodules

## Manual approach

### Create a volume for filesystem API exposure

`docker volume create -d local -o type=none -o device=/tmp/api -o o=bind api_volume`


### Build image

To build the image please follow the steps:

#### As the-Container-User:

`cd <this repo>`

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_vis:latest cyclomatic_complexity`

#### As the-Container-Developer:

In case you wondered how to amend or enhance the current functionality by changing the API, please follow this path:

`cd <this repo>`

Modify API queries adding or changing JSON schemas in `API/*.json` and execute the cmd:

`cp submodules or main>/API/* > <submodules or main>/cyclomatic_complexity/API/`

Compose and put your scripts `*_exec.sh` carrying out processing of added queries logic into `<submodules or main>/cyclomatic_complexity/services` directory.

Finally, generate the image by itself. To do that, execute the next cmd:

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_vis:latest cyclomatic_complexity`

In case you found your API and its processors in `*_exec.sh` satisfying, please make the changes permanent and embody those script generation as automation step by putting them into the appropriate module `<submodules or main>/cyclomatic_complexity/api_generator.py`

### Launch a container from the image

#### Go to your C/C++ project directory:

`cd <your project directory>`

 and run

`mkdir api.pmccabe_collector.restapi.org`

`chmod 777 api.pmccabe_collector.restapi.org`

The `777` allows docker `pmccabe_collector` service to access this mount point which belong to the host filesystem which would have become unavailable otherwise.

#### Run the container in your project directory

`sudo docker run -it --mount type=bind,src=./,target=/mnt pmccabe_vis:latest`

Having all steps acomplished and with no erros in a processing logic, the content representing pseudo filesystem appears by path `<your project directory>/api.pmccabe_collector.restapi.org`. Typically it contains the `cc` directory (stands for Cyclomatic Complexity) and `README-CC-*.md` file for API instructions.
In none of those file are appeared, then other different failures have taken place. I'd very appreciate for any documented issues. In my own experience the essential utility `pmccabe` crashed when I was tried to estimate complexity of a Linux kernel project.

# Submodules

It's possible to enhance the main functionality significantly by employing additional dependent services. I strongly recommend your refer to the [README.md](submodules/README.md) file located the `submodules` directory
