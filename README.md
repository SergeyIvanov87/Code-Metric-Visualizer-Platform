# pmccabe_visualizer_docker
Docker image for `pmccabe_visualizer`

# Build image

To build the image please use the following command:

`sudo docker build -t pmccabe_vis:latest .`

# Launch a container from the image

`sudo docker run -it --mount type=bind,src=/tmp,target=/mnt pmccabe_vis:latest <Git repo address>`
