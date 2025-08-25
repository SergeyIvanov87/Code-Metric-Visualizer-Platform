# HTTP FS API Proxy

A main purpose of this sidecar container is to redirect request of an upstream service to an outter service using HTTP transport rather than leveraging filesystem API.

The filesystem API has a drawback that both services must reside on a same machine and connected by using a mechanism of shared folders or volumes.
To overcome that limitation this `HTTP FS API Proxy` was designed. Employing this sidecar container allow us to break that infrastructure dependnecy between upstream and downstream services taking advantage of a dependency inverstion approach.

In this terminology a `UPSTREAM_SERVICE` is the one who initiates requests using public API of this `HTTP FS API Proxy` interface and a `DOWNSTREAM_SERVICE` is the service which perform an actual logic to serve those requests respectively.
As it is a very common situation that one `UPSTREAM_SERVICE` is linked to multiple `DOWNSTREAM_SERVICE`'s, the `HTTP FS API Proxy` is designed to be independent on each other proxy instances, so that users of that sidecar could build various configurations according to their needs.

To reflect the fact that different `DOWNSTREAM_SERVICE`'s  may be achieved either through a common application gateway or be resided on different nodes physically, the `HTTP FS API Proxy` offers the `DOWNSTREAM_SERVICE_NETWORK_ADDR`, which represents a serving node connection point.
This `DOWNSTREAM_SERVICE_NETWORK_ADDR` has flexible meaning:

a) it could have a same value as the `DOWNSTREAM_SERVICE`( or absent) to take advantage of a "service discovery approach" (NOT IMPLEMENTED yet)

b) it could be a DNS address of the `DOWNSTREAM_SERVICE` or the application gateway, but that is up to users to take care of names resolution problem in their network

c) it could be an IP address of the `DOWNSTREAM_SERVICE`

## Prerequisites

A service described by `UPSTREAM_SERVICE` MUST met the requirements:

- to implement [all_dependencies](../../common/API/all_dependencies.json) API
- to implement [unmet_dependencies](../../common/API/unmet_dependencies.json) API

Otherwise the `HTTP FS API Proxy` won't discover any queries to proxy

## How to build the HTTP FS API Proxy

`docker build -f fs_api_proxy/http_proxy/Dockerfile -t fs_api_proxy_http:latest .`

## How to launch HTTP FS API Proxy

`docker run -it --env=UPSTREAM_SERVICE=<your data> --env=DOWNSTREAM_SERVICE=<your data> --env=DOWNSTREAM_SERVICE_NETWORK_ADDR=<your data> fs_proxy:latest`

#### Where:

- `UPSTREAM_SERVICE` - is a name of a service which initiates queries to other services and need these queries to be proxied

- `DOWNSTREAM_SERVICE` - is a name of one of those services which queries are going to be proxied to. Please pay attention that `DOWNSTREAM_SERVICE` is a service name as it declared in `API/deps` or in the project main directory

- `DOWNSTREAM_SERVICE_NETWORK_ADDR` - is an implementation dependent (DNS, IP at the moment) network address of a node which implements a service described by `DOWNSTREAM_SERVICE`
