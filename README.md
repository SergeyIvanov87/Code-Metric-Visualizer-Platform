# pmccabe_visualizer_docker

Docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer
The service is supposed to monitor cyclomatic complexity of a C/C++ project

The service implementation is still in progress and it has the very limited functionality.
The service is available as a `copilot`-based feature which has named `pmccabe_collector`. Only `pmccabe_collector` local-machine (Linux tested only) docker image is shipping at the moment.
The purpose of `pmccabe_collector` is to reach a similar functionality as it enhanced by the `sidecar` pattern which goal here is to extend software developing experience.
Launching `pmccabe_collector` and binding docker shared folder into your existing C/C++ project directory, allow this container to populate filesystem API entrypoints, which are served for communicating with the `pmccabe_collector` docker service.
Please check on existing API:
![alt text](https://github.com/SergeyIvanov87/pmccabe_visualizer_docker/blob/main/API.fs?raw=true)

According to REST ideology, the request could represent a particular hierarcy structure, thus `pmccabe_collector` leverages this idea and maps those API requests as nodes mapped to a filesystem hierarchy like as directory and files inside `api.pmccabe_collector.restapi.org` populated API entrypoint inside your project directory.
Each `GET` request can be executed as simple ACCESS-operation on a file named `get` in the bottom of relevant filesystem hierarchy in the same way as `/proc` filesystem employed in order to read (and/or store) some system settings.

For example:
The request `GET     api.pmccabe_collector.restapi.org/main/xml` can be triggered in the filesystem API mapped notation as:
`cat api.pmccabe_collector.restapi.org/main/xml/get`

This file-based interface is only API supported at the moment.

# Build image

To build the image please use must follow the steps:

- At first you need to generate API request handlers as a simple self-generated bash scripts. Using this generator is important for developing process only to make sure that changes of API file would not be forgotten
`cd local`
`./build_local_api.py devel API.fs /mnt`

Don't worry, the directory `/mnt` is supposed to be a part of container filesystem

- Next you need to generate the image by itself. To do that, execute the next cmd in the same `local` directory:
`sudo docker build -t pmccabe_vis:latest .`

# Launch a container from the image

- Go to your C/C++ project direcotory:
`cd <your project directory>`
 and run
`mkdir api.pmccabe_collector.restapi.org`
`chmod 777 api.pmccabe_collector.restapi.org`

The `777` allows docker `pmccabe_collector` service to access this mount point which belong to the host filesystem which would have become unavailable otherwise

- Run the container in your project directory
`sudo docker run -it --mount type=bind,src=./,target=/mnt pmccabe_vis:latest`
