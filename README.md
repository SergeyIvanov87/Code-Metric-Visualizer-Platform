# pmccabe_visualizer_docker

The docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer

The service is supposed to monitor cyclomatic complexity of a C/C++ project.

The service implementation is still in progress and it has the very limited functionality.
The service is available as a `copilot`-based feature which has named `pmccabe_collector`. Only `pmccabe_collector` local-machine (Linux tested only) docker image is shipping at the moment.
The purpose of `pmccabe_collector` is to reach a similar functionality as it enhanced by the `sidecar` pattern which goal here is to extend software developing experience.
Launching `pmccabe_collector` and binding a docker shared folder into your existing C/C++ project directory, allow this container to populate filesystem API entrypoints, which are served for communicating with the `pmccabe_collector` docker service.
Please check on the existing pseudo-filesystem API:
[API](local/API.fs)

According to the REST ideology, a request could represent a particular hierarcy structure, thus `pmccabe_collector` leverages this idea and maps those API requests as nodes mapped to a filesystem hierarchy like as directories and files inside the populated API-entry point `api.pmccabe_collector.restapi.org` resided in your project directory.
Each request can be executed as simple ACCESS-operation on a file named `exec` in the bottom of relevant filesystem hierarchy in the same way as the Linux `/proc` pseudo-filesystem employed in order to read (and/or store) some system settings.

#### For example:

The request

`GET api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph`

can be triggered in the filesystem API mapped notation as:

`cat api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph/GET/exec`

If you prefer to use GUI rather than CLI, then just open a path `api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph` in your favorite File Manager. It is realy simple as it sounds! Regardless an approach you use, nevertheless you'll find the outcome of your query execution, usually meant a file, in the same directory where the original `exec` API-file located. Feeling curiosity or discovering any other ways to alter the result of query execution, it's possible to wander through such API filesystem content and play with a different kind of file nodes called parameters. Changing a value in these parameter-files you can affect the result (or view) of a request outcome.
Typical use-case is add filtering `thirdparty` directories as `watch_list`. You can acrhive that by changing values of the parameters `0.-regex` and `1.-prune` resided by path `api.pmccabe_collector.restapi.org/project/{uuid}`, which actually represent parameters for the  well-known command `find` from the general command manual `man find`.

This file-based interface is only container API supported at the moment.

# Build image

To build the image please follow the steps:

#### The-Container-Developer:

As a first step, you need to generate API request handlers in a form of simple self-generated bash scripts. This script production phase is important step for developing process only, because it reassure that any changes in the basic API-file would not be forgotten.
       
`cd <this repo>`
 
`python ./build_api.py API > local/API.fs`
  
`cd local`
 
`python ./build_local_api.py devel API.fs /mnt`

Don't worry, the directory `/mnt` is supposed to be a part of container filesystem

Next you need to generate the image by itself. To do that, execute the next cmd in the same `local` directory:
  
`sudo docker build -t pmccabe_vis:latest .`

#### The-Container-User:
   
 `cd <this repo>`
 
 `cd local`
 
 `python ./build_local_api.py devel API.fs /mnt`
 
 `sudo docker build -t pmccabe_vis:latest .`
   

# Launch a container from the image

### Go to your C/C++ project directory:
  
`cd <your project directory>`

 and run
 
`mkdir api.pmccabe_collector.restapi.org`

`chmod 777 api.pmccabe_collector.restapi.org`

The `777` allows docker `pmccabe_collector` service to access this mount point which belong to the host filesystem which would have become unavailable otherwise.

### Run the container in your project directory
  
`sudo docker run -it --mount type=bind,src=./,target=/mnt pmccabe_vis:latest`

The service will build two files: 
- `init.xml`(which contains "database" of `pmccabe` metric for a project components/files/functions - see `man pmccabe`)
- `init.svg` (an interactive flamegraph simplifies such metric representation; to study more about "flamegraph", please elaborate on https://github.com/brendangregg/FlameGraph#3-flamegraphpl)

In none of those file are appeared, then other different failures have taken place. I'd very appreciate for any documented issues. In my own experience the essential utility `pmccabe` crashed when I was tried to estimate complexity of a Linux kernel project.
