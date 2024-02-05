# REST API Image

It's very important to provide a convenient interface for comfortable using of any kind of service.

*REST API* is the most popular set of rules and it brings up favourable user experience because it's either pretty easier to manipulate services by using a corny web browser or to carry out automated requests from a command line interface and having the predefined conventional feedback in result.

This image is developed as an `ambassador` service representing the main servide and its submodules as an application gateway. This representation encompasses gathering all available pseudo filesystem API PIPEs nodes and unveils them as typical REST queries: **GET**, **POST** etc.

After being started, the container launches a simple WEB-server providing the entry point of REST API communication to the main service and its complementary services as a submodules.
The root URI represents the main index-page comprises all **`*.md`** manual-pages of all registered services it gathered. Therefore, it's important for service developers to supplement their containers with an holistic API description accompanied by a **README.md** file.

Once started, as being said before, the REST-API service searches for all registered services by parsing filesystem tree using  the set of predefined rules:

1. A pseudo filesystem API request MUST be represented by a valid path terminated by a method: **GET**, **POST**, **PUT** etc. On the depth of these tree hierarchy there MUST be special PIPE files **exec** and **result<.EXT >** located. Where **<.EXT >** MUST be stand for a valid **Content-Type** header of the particular REST request.

2. A pseudo filesystem API request SHOULD be accompanied by a markdown description file **`*.md`.** detectable in the filesystem tree

The rule **1.** allows the request be executed using HTTP request using the same valid path as and URI and by the regarding HTTP method

The refinement **2.** allows the request to be enumerated in the API entrance list discoverable on root URI index page loading. This trivial option simplified navigation and usability tredemendously.

The description format MUST comprise:

* a request name next after ## (Heading Level 2)

* a request **URI** terminated by a **`Method`** next after ### (Heading Level 3).

Please refer to the [make_api_readme.py](../../local/make_api_readme.py) and  the `Description` section of an [API request example](../../API/watch_list.json)


# Build the container

From the main repository directory run:

`sudo docker build submodules/rest_api/ -t pmccabe_rest:latest`

# Run the container from submodules

The main image is supposed to create an unnamed `volume` which acts as a shared storage which provides some environments initialized accompatined by important API utilites as python modules.
Submodule-image relies on that `contract` provided by the main image and must adhere to it, thus the command to launch any submodule-container accompanied by an additional argument `--volumes-from <name or id of the main container>` and might looks like:

`sudo docker run -it --mount type=bind,src=./,target=/mnt --volumes-from 5b60b21fe9f8 -p 5000:5000 pmccabe_rest:latest`

where `5b60b21fe9f8` is a main container ID
