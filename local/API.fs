flamegraph	GET	api.pmccabe_collector.restapi.org/main/statistic/view/flamegraph	--width=1200	--height=16
watch_list	GET	api.pmccabe_collector.restapi.org/main	-regex=".*\.\(hpp\|cpp\|c\|h\)"	-prune=! -path "*buil*" ! -path "*thirdpart*"
statistic	GET	api.pmccabe_collector.restapi.org/main/statistic	-mmcc=1,	-tmcc=1,	-sif=1,	-lif=1,
view	GET	api.pmccabe_collector.restapi.org/main/statistic/view	-attr=mmcc,tmcc,sif,lif
