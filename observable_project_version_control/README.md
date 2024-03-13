docker volume create -d local -o type=none -o device=/tmp/docker -o o=bind api.pmccabe_collector.restapi.org
docker run -it --name project -v api.pmccabe_collector.restapi.org:/api -e PROJECT_URL=https://github.com/SergeyIvanov87/TrafficInspector.git -e PROJECT_BRANCH=master project_vc:latest
