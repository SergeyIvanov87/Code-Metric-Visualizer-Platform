# Submodules

Submodules provide extended functionality by introducing additional features built on top of the main module.

The instruction how to built the submodules is quite similar with the main image creation steps and encompass the following procedures (the `rrd` submodule is considered):

#### The-Container-Developer:

As a first step, you need to generate API request handlers in a form of simple self-generated bash scripts. This script production phase is important step for developing process only, because it reassure that any changes in the basic API-file would not be forgotten.

`cd <this repo>`

Modify API queries adding or changing JSON schemas in `/submodules/rrd/API/*.json` and execute the cmd:

`python ./build_api.py submodules/rrd/API > submodules/rrd/local/API.fs`

Modify `submodules/rrd/local/api_generator.py` in order to generate a proper serving script for particulat API query which was published in `submodules/rrd/API/*.json`

`python local/build_api_executors.py submodules/rrd/local/API.fs submodules/rrd/local -o submodules/rrd/local/services`

Thats almost done! Next you need to generate the image by itself. To do that, execute the next cmd:

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_rrd_analytic:latest submodules/rrd/local/`

#### The-Container-User:

`cd <this repo>`

`python local/build_api_executors.py submodules/rrd/local/API.fs submodules/rrd/local -o submodules/rrd/local/services`

`DOCKER_BUILDKIT=1 sudo docker build -t pmccabe_rrd_analytic:latest submodules/rrd/local/`
