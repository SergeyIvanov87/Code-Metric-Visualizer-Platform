flamegraph	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph	--width=1200	--height=16
watch_list	GET	api.pmccabe_collector.restapi.org/project/{uuid}	-regex=".*\.\(hpp\|cpp\|c\|h\)"	-prune=! -path "*buil*" ! -path "*thirdpart*"
statistic	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/statistic	-mmcc=1,999999	-tmcc=1,999999	-sif=1,999999	-lif=1,999999
view	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view	-attr=mmcc,tmcc,sif,lif
