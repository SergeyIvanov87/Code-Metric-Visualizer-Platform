# K8S

# Minikube

During experiments with `minikube` I couldn't make `minikube` working using `driver==docker` option,
thus further instructions are written in assumption that KVM is set and enabled on your Linux machine where the `minikube` cluster is set up

## Prerequisites
### 1. VPN

Ensure your VPN service is turned off and down, otherwise conflicts with dockerm virtual interfaces and names resolution are taked place.

### 2. Docker

Ensure that `docker` configured as root-less and all reguired permissions are set and the current user has been added into group `docker`.
Doing that check your OS documentation, typical steps include but not limited to the following:

0. put your current user into `docker` group

1. Create `/etc/subuid` and `/etc/subgid` with the following:

    `testuser:231072:65536`

        ### replace 'testuser' with your username.

2. Enable socket-activation for the user service:

    `systemctl --user enable --now docker.socket`

3. Finally set docker socket environment variable:

    `export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock`

You can also add it to `~/.bashrc` or somewhere alike.


Ensure that docker service is stopped by running

`systemctl status docker.service`

The service must be stopped and inactve. The set up doesn't require this service running up, the docker service will be started on demand.
To make it possible, ensure that `docker.socket` is enabled for the current user:

`systemctl enable docker.socker`

Ensure that docker is accessible by running

`docker info`


## Setting a minikube cluster up

### 1. using KVM driver

Start the virtualization service

`sudo systemctl start libvirtd.service`

Ensure that the virtualization service is up and running

`sudo systemctl status libvirtd.service`

To do not specify the `driver` every time launching a cluster, set the default driver as

`minikube config set driver kvm2`

After that it's possible to launch the minikube cluster

`minikube start`


#### Using a local machine docker storage

If you want to pull out docker images on pods inside the minikube cluster using a local machine docker storage rather than DockerHub etc., give access minikube to the local docker environment

`eval $(minikube docker-env)`

##### Build an entire image set

Upon the building process finishes, the ldocker compose will store it in the local docker storage

`docker compose -f compose-analytic-http-api.yaml build`

or

`DOCKER_BUILDKIT=0 docker compose -f compose-analytic-http-api.yaml build`

## Deployment

1. Run the Deployment as a multi container pod responsible for CC measurement:

    `kubectl apply -f k8s/deployment/cc_visualizer-http.yaml`

    Ensure that the Deployment is up and running

    `kubectl get deploy`

    Ensure that a pod has started and initialized:

    `kubectl get pods`

    All required events are signalled and there are no errors or warnings

    `kubectl events pods`

    You can check logs of a specific container resided on a POD individually

    `kubectl logs <your POD> -c <container on the POD>`

    If something has happened unexpectedly, you can connect to the failed container

    `kubectl exec <your POD> -it -c <container on the POD> -- /bin/bash`


2. Assuming that the Deployment launched successfully, we run a Service to allow communicate the Deployment communicate to the outside world


    `kubectl apply -f k8s/service/cc_visualizer-http.yaml`

    Ensure that the Service is up and running

    `kubectl get svc`


3. Now you can check that the service `cc_visualizer-http` available:

    * From inside the cluster using the DNS name `cc_visualizer-http` on port `5001`

    * From outside the cluster by hitting any of the cluster nodes on port `30001`
