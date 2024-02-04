# REST API Image

It's very important to provide a convenient interface for comfortable using of any kinf of service.

REST API is the most popular and leads to favourable user experience because it's either pretty easier to manipulate it using a web browser or to carry out automated requests from a command line interface having the predefined conventional feedback.
This image is developed as an 'ambassador' service representing the main servcie and its submodules as an application gateway. This representation encompasses gathering all available pseudo filesystem API PIPEs nodes and unveils them as typical REST queries: GET, POST etc.

After being started, the container launches a simple WEB-server which the main index-page comprises all `*.md`


# Run a container from submodules

The main image is supposed to create an unnamed `volume` which acts as a shared storage which provides some environments initialized accompatined by important API utilites as python modules.
Submodule-image relies on that `contract` provided by the main image and must adhere to it, thus the command to launch any submodule-container accompanied by an additional argument `--volumes-from <name or id of the main container>` and might looks like:

`sudo docker run -it --mount type=bind,src=./,target=/mnt --volumes-from 5b60b21fe9f8 pmccabe_rest:latest -p 5000:5000`

where `5b60b21fe9f8` is a main container ID
