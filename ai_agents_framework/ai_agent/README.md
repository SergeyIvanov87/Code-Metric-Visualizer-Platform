`LOCAL_HOST_MOUNT_POINT=<local host mount point> && mkdir -p ${LOCAL_HOST_MOUNT_POINT} && chmod 777 ${LOCAL_HOST_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${LOCAL_HOST_MOUNT_POINT} -o o=bind api.pmccabe_collector.restapi.org`
`SRC_MOUNT_POINT=ai_agent/sources  && docker volume create -d local -o type=none -o device=${SRC_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.src`
`MODEL_ASSETS_MOUNT_POINT=<artefacts storage path> && mkdir -p ${MODEL_ASSETS_MOUNT_POINT} && chmod 777 ${MODEL_ASSETS_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${MODEL_ASSETS_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.asssets.models`
`RAG_ASSETS_MOUNT_POINT=<RAG assets storage path> && mkdir -p ${RAG_ASSETS_MOUNT_POINT} && chmod 777 ${RAG_ASSETS_MOUNT_POINT} && docker volume create -d local -o type=none -o device=${RAG_ASSETS_MOUNT_POINT} -o o=bind api.pmccabe_collector.ai_agent.asssets.rag`

`docker build -t ai_agent:latest -f ai_agent/Dockerfile .`
`docker run -it --name ai_agent -v api.pmccabe_collector.restapi.org:/api -v api.pmccabe_collector.ai_agent.asssets.rag:/assets/rag -v api.pmccabe_collector.ai_agent.asssets.models:/assets/models -v api.pmccabe_collector.ai_agent.src:/package ai_agent:latest`
