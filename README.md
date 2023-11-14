# pmccabe_visualizer_docker
Docker image for `pmccabe_visualizer` https://github.com/SergeyIvanov87/pmccabe_visualizer
The service is supposed to monitor cyclomatic complexity of a project (only github.com is supported at now)

The service implementation is in progress and has it has the very limited functionality:
- file-based interface is supported:
    - Once the service started, it builds the project metrics and store corresponded files (`*.xml`, `*.svg`) in a shared folder, which must have been populated using `bind` mount at docker starting.
    - removing this files causes resetting the repo local branch to upstream HEAD and the service starts rebulfing pmccabe metrics, the files will be recalculated again.
    - putting `*.patch` file triggers pmccabe metric calculation and then `*.xml`,`*.svg` files will appear in the shared folder.
- no focusing on hot-places, each patch triggers entiry project metric reconstruction

# Build image

To build the image please use the following command:

`sudo docker build -t pmccabe_vis:latest .`

# Launch a container from the image

`sudo docker run -it --mount type=bind,src=/tmp,target=/mnt pmccabe_vis:latest <your git repo address> <your branch>`
