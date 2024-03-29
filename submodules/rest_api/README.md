# REST API Image

It's very important to provide a convenient interface for comfortable use of any kind of services.

*REST API* is the most popular set of rules and it brings up favourable user experience because it's either pretty easier to manipulate services by using a corny web browser or to carry out automated requests from a command line interface and having the predefined conventional feedback in result.

This image is developed as an `ambassador` service representing the main service and its submodules as an application gateway. This representation encompasses gathering all available pseudo filesystem API PIPEs nodes and unveils them as typical REST queries: **GET**, **POST** etc.

After being started, the container launches a simple WEB-server providing the entry point of REST API communication to the main service and its complementary services as submodules.
The root URI represents the main index-page comprising all **`*.md`** manual-pages from all registered services which were recognized. Therefore, it's important for service developers to supplement their containers with a holistic API description accompanied by a **README.md** file.

Once started, as being said before, the REST-API service searches for all registered services by parsing the filesystem tree using the set of predefined rules:

1. A pseudo filesystem API request **MUST** be represented by a valid path terminated by a particular method from the valid HTTP request list: **GET**, **POST**, **PUT** etc. On the depth of these tree hierarchies there **MUST** be special PIPE files **exec** and **result<.EXT >** resided. Where **<.EXT >** **MUST** stand for a valid **Content-Type** header of the particular REST request.

2. A pseudo filesystem API request **SHOULD** be accompanied by a markdown description file **`*.md`.** detectable in the filesystem tree

The rule **1.** allows the request be executed using HTTP request using the same valid path as and URI and by the regarding HTTP method

The refinement **2.** allows the request to be enumerated in the API entrance list discoverable on root URI index page loading. This trivial option simplified navigation and usability tremendously.

The description format **MUST** comprise:

* a request name next after ## (Heading Level 2)

* a request **URI** terminated by a **`Method`** next after ### (Heading Level 3).

Please refer to the [make_api_readme.py](../../cyclomatic_complexity/make_api_readme.py) and  the `Description` section of an [API request example](../../API/watch_list.json)


# Prerequisites

### General

- You **MUST** configure a docker volume `api.pmccabe_collector.restapi.org`, which will represent the point of service communications, by executing the following command:

    `mkdir -p <local host mount point> && chmod 777 <local host mount point> && docker volume create -d local -o type=none -o device=<local host mount point> -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

- You **SHOULD** define environment variables `FLASK_RUN_HOST` and `FLASK_RUN_PORT` to determine where REST API service will listen incoming connections (default values `0.0.0.0` and `5000` respectfully).

### Analytic UC

- You **SHOULD** define environment variables `FLASK_RUN_HOST` and `FLASK_RUN_PORT` to determine where REST API service will listen incoming connections (default values `0.0.0.0` and `5000` respectfully).


# Build & Run image

### Analysis UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rest_api:latest -f submodules/rest_api/Dockerfile submodules/rest_api`

Launching depends on [cyclomatic_complexity](../../cyclomatic_complexity), [rrd](../rrd), thereby launch the `cc_visualizer`, `rrd_analytic` images at first.

`docker run -it --name rest_api -v api.pmccabe_collector.restapi.org:/api -e FLASK_RUN_PORT=6666 -e FLASK_RUN_HOST=0.0.0.0 --volumes-from cc_visualizer rest_api:latest`


### Analytic UC

From the main repository directory run:

`DOCKER_BUILDKIT=1 docker build -t rest_api:latest -f submodules/rest_api/Dockerfile submodules/rest_api`

Launching depends on [cyclomatic_complexity](../../cyclomatic_complexity), [rrd](../rrd), [observable_project_version_control](../../observable_project_version_control), thereby launch the `cc_visualizer`, `rrd_analytic`, `vcs_project` images at first.

`docker run -it --name rest_api -v api.pmccabe_collector.restapi.org:/api -e FLASK_RUN_PORT=5000 -e FLASK_RUN_HOST=0.0.0.0 --volumes-from cc_visualizer -p 5000:5000 rest_api:latest`
