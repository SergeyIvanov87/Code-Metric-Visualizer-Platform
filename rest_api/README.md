# REST API Image

It's very important to provide a convenient interface for comfortable use of any kind of services.

*REST API* is the most popular set of rules and it brings up favourable user experience because it's either pretty easier to manipulate services by using a corny web browser or to carry out automated requests from a command line interface and having the predefined conventional feedback in result.

This image is developed as an `ambassador` service representing the main service and its submodules as an application gateway. This representation encompasses gathering all available pseudo filesystem API PIPEs nodes and unveils them as typical REST queries: **GET**, **POST** etc.

After being started, the container launches a simple WEB-server providing the entry point of REST API communication to the main service and its complementary services as submodules.
The root URI redirects to the API landing page, which lists the discovered service containers. A container is identified by the first path component after the API domain prefix (for example, `cyclomatic_complexity` in `api.pmccabe_collector.restapi.org/cyclomatic_complexity/statistic`). Queries directly below the domain remain ungrouped on the landing page. Select a container to open its API list, then select a query to configure its parameters before execution. Services should publish a **README.md** file with their API documentation; the existing README discovery and restart cycle also rebuilds these pages when APIs appear or disappear.

Browser pages live under `/<API domain>/_browse/services/<container>` and `/<API domain>/_browse/queries/<query ID>`. They do not execute filesystem queries. The service page preserves each query's recovered markdown documentation and replaces the generated immediate-execution links with links to its parameter page. When a collected README is present, only its documented query entries appear in the browser, preserving README-driven publication and withdrawal. Direct action routes continue to follow the discovered FIFOs.

Each supported filesystem API method has its own template (`query_get.html`, `query_put.html`, and `query_post.html`) extending the shared query form. Text fields contain the defaults recovered from the filesystem argument files, including inherited parameters from parent directories. If a parameter is defined at multiple levels, the default closest to the query wins. `SESSION_ID` remains managed by the server.

Select **Execute query** to send the declared HTTP method with only edited parameters encoded in the query string. Unchanged fields are omitted so providers retain their own defaults, including inherited quotes and backslashes. The page reports the HTTP status and provides a link to open the returned result, including binary results. JavaScript is required for this execution control. Existing direct API URLs, query-string parameters, the `default` option, and HEAD readiness probes remain available to programmatic clients. The `default` option sends no parameter overrides: providers read their own parameter files, preserving quoted defaults across filesystem API calls. A browser GET to a POST-only API URL redirects to its parameter page.

Only the API action paths are published in the HTTP route discovery document; browser pages use the generic REST provider's existing gateway fallback. Provider order and route precedence are unchanged. Multiple methods on one action path are advertised once.

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

    `LOCAL_HOST_MOUNT_POINT=<local host mount point> && mkdir -p ${LOCAL_HOST_MOUNT_POINT} && chmod 777 ${LOCAL_HOST_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${LOCAL_HOST_MOUNT_POINT} -o o=bind api.pmccabe_collector.restapi.org`

### Analysis UC

- You **SHOULD** define environment variables `FLASK_RUN_HOST` and `FLASK_RUN_PORT` to determine where REST API service will listen incoming connections (default values `0.0.0.0` and `5000` respectfully).

### Analytic UC

- You **SHOULD** define environment variables `FLASK_RUN_HOST` and `FLASK_RUN_PORT` to determine where REST API service will listen incoming connections (default values `0.0.0.0` and `5000` respectfully).


# Build & Run image

### Analysis UC

From the main repository directory run:

`docker build -t rest-api:latest -f rest_api/Dockerfile .`

Launching depends on [cyclomatic_complexity](../cyclomatic_complexity), [rrd](../rrd), thereby launch the `cc-visualizer`, `rrd-analytic` images at first.

`docker run -it --name rest-api -v api.pmccabe_collector.restapi.org:/api -e FLASK_RUN_PORT=6666 -e FLASK_RUN_HOST=0.0.0.0 --volumes-from cc-visualizer rest-api:latest`


### Analytic UC

From the main repository directory run:

`docker build -t rest-api:latest -f rest_api/Dockerfile .`

Launching depends on [cyclomatic_complexity](../cyclomatic_complexity), [rrd](../rrd), [observable_project_version_control](../observable_project_version_control), thereby launch the `cc-visualizer`, `rrd-analytic`, `vcs-project` images at first.

`docker run -it --name rest-api -v api.pmccabe_collector.restapi.org:/api -e FLASK_RUN_PORT=5000 -e FLASK_RUN_HOST=0.0.0.0 --volumes-from cc-visualizer -p 5000:5000 rest-api:latest`

# Testing the container

### Standalone container functional test

Executable REST tests belong in `tests/functional/service_tester/` and run only
through the tester Dockerfile's `/tests/init.sh /tests /api` entrypoint. The
browser checks use the predefined JSON queries under `tests/functional/data/`
and the existing Compose service at `http://rest-api:5000`. They check grouped
navigation, parameter fields, execution links, submitted field values, and
quoted defaults. They do not start an additional Flask application.

From the main repository directory run:

`docker compose -f rest_api/compose-functional.test.yaml build`

and then

`docker compose -f rest_api/compose-functional.test.yaml up --abort-on-container-exit --exit-code-from rest-api-functional-service-tester`

Do not invoke individual Python or JavaScript tests directly. Agent-local
reproduction must use a temporary Python environment prepared according to the
tester Dockerfile, then invoke its `init.sh` with the declared arguments. See
[container test diagnostics](../.agents/skills/container-test-diagnostics/SKILL.md).

### Optional proxy CA certificate

The Compose configurations accept an optional `PROXY_CA_FILE`: an **absolute
path** to a PEM CA certificate or CA bundle, readable by the container's service
user. No environment-specific certificate path is assumed.

Without an additional CA, use the normal commands:

```sh
docker compose -f rest_api/compose-functional.test.yaml build
docker compose -f rest_api/compose-functional.test.yaml up --abort-on-container-exit --exit-code-from rest-api-functional-service-tester
```

Behind a TLS-inspecting proxy, set the certificate path for both commands:

```sh
export PROXY_CA_FILE=/absolute/path/to/company-proxy-ca.pem
docker compose -f rest_api/compose-functional.test.yaml build
docker compose -f rest_api/compose-functional.test.yaml up --abort-on-container-exit --exit-code-from rest-api-functional-service-tester
```

An unset or empty variable selects the shared empty PEM file in
`common/proxy_setup_image_helpers/`. An explicitly
provided empty file also adds no trust and needs no special handling. A nonempty
CA file extends the normal system trust; TLS verification stays enabled. An
explicitly configured nonexistent file is a configuration error. Only provide
public CA certificates here, never private keys.

The shared `common/proxy_setup_image_helpers/compose-proxy-trust.yaml`
defines one `proxy_ca` secret. Compose entrypoints import it through `include`;
services explicitly reference it for builds or runtime. `extends` alone does
not import top-level resources.

BuildKit mounts the file as the optional `proxy_ca` secret during package
installation. The shared `with-proxy-ca.sh` wrapper handles trust setup, command
execution, exit status, signal forwarding, and cleanup. The combined trust
bundle is removed in the same build step, so
additional certificates do not enter image layers. Direct `docker build` works
without a secret; optionally pass `--secret id=proxy_ca,src=/path/to/ca.pem`.
The isolated REST Dockerfile supports the same secret.

The REST service needs the CA only while building. Flask and Markdown are
installed by apk in the image; the watchdog loads generated source directly
without installing packages or contacting package indexes at startup/restart.
Consequently, the REST runtime has no proxy CA secret mount or wrapper entrypoint.

Proxy routing remains configured through Docker's standard proxy settings;
`PROXY_CA_FILE` configures trust, not the proxy address. REST functional services
append their internal REST hostname and loopback addresses to `NO_PROXY` and
`no_proxy` so local requests do not go through an outbound proxy. Build secrets do not invalidate the
Docker build cache; use `build --no-cache` when you need to re-exercise package
installation with a changed CA.
