# pmccabe_visualizer_docker

Docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer
The service is supposed to monitor cyclomatic complexity of a C/C++ project

The service implementation is still in progress and it has the very limited functionality.
The service is available as a `copilot`-based feature which has named `wingman`. Only `wingman` docker image is shipping at the moment.
The purpose of `wingman` is to provide a `sidecar` pattern which goal here is to extend software developing experience.
Launching `wingman` and binding docker shared folder into your existing C/C++ project directory, allow this container to populate filesystem API entrypoints, which are served to communicate to the `wingman` docker service.
Please check on existing API:
![alt text](https://github.com/SergeyIvanov87/pmccabe_visualizer_docker/blob/main/API.fs?raw=true)

According to REST ideology, the request could represent a particular hierarcy structure, thus `wingman` leverages this idea and maps those API requests as nodes mapped to a filesystem hierarchy like as directory and files inside `wingman.org` populated API entrypoint inside your project directory.
Each `GET` request can be executed as simple ACCESS-operation on a file named `get` in the bottom of relevant filesystem hierarchy in the same way as `/proc` filesystem employed in order to read (and/or store) some system settings.

For example:
The request `GET     wingman.org/main/xml` can be triggered in the filesystem API mapped notation as:
`cat wingman.org/main/xml/get`

This file-based interface is only API supported at the moment.

# Build image

To build the image please use must follow the steps:

- At first you need to generate API request handlers as a simple self-generated bash scripts. Using this generator is important for developing process only to make sure that changes of API file would not be forgotten
`cd wingman`
`./build_local_api.py devel API.fs /mnt`

Don't worry, the directory `/mnt` is supposed to be a part of container filesystem

- Next you need to generate the image by itself. To do that, execute the next cmd in `wingman` directory:
`sudo docker build -t pmccabe_vis:latest .`

# Launch a container from the image

- Go to your C/C++ project direcotory and run
`mkdir wingman.org`
`chmod 777 wingman.org`

The `777` allows docker `wingman` service to access this mount point which belong to the host filesystem which would have become unavailable otherwise

- Run the container
`sudo docker run -it --mount type=bind,src=/tmp,target=/mnt pmccabe_vis:latest`
