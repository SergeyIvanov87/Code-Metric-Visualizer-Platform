flamegraph	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph	--width=1200	--height=16
watch_list	GET	api.pmccabe_collector.restapi.org/project/{uuid}	-regex=".*\.\(hpp\|cpp\|c\|h\)"	-prune=! -path "*buil*" ! -path "*thirdpart*"
statistic	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/statistic	-mmcc=1,	-tmcc=1,	-sif=1,	-lif=1,
analytic	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/analytic	--start=1701154260	--step=1	--no-overwrite=	NO_NAME_PARAM.0=DS:mmcc:GAUGE:1y:U:U	NO_NAME_PARAM.1=RRA:LAST:0.1:1:100000
view	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view	-attr=mmcc,tmcc,sif,lif
