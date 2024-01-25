# Run a container from submodules

The main image is supposed to create an unnamed `volume` which acts as a shared storage which provides some environments initialized accompatined by important API utilites as python modules.
Submodule-image relies on that `contract` provided by the main image and must adhere to it, thus the command to launch any submodule-container accompanied by an additional argument `--volumes-from <name or id of the main container>` and might looks like:

`sudo docker run -it --mount type=bind,src=./,target=/mnt --volumes-from 5b60b21fe9f8 pmccabe_rest:latest -p 127.0.0.1:80:5000`

where `5b60b21fe9f8` is a main container ID
