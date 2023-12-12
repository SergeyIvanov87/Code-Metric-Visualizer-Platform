flamegraph	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view/flamegraph	--width=1200	--height=16
rrd_view_graph	GET	api.pmccabe_collector.restapi.org/project/{uuid}/analytic/rrd/view/graph	?colors?=
watch_list	GET	api.pmccabe_collector.restapi.org/project/{uuid}	-regex=".*\.\(hpp\|cpp\|c\|h\)"	-prune=! -path "*buil*" ! -path "*thirdpart*"
statistic	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/statistic	-mmcc=1,	-tmcc=1,	-sif=1,	-lif=1,
rrd_view_get	GET	api.pmccabe_collector.restapi.org/project/{uuid}/analytic/rrd/view	-s=1701154260	-e=None	package_counters=mmcc_mean,mmcc_median,mmcc_deviation,tmcc_mean,tmcc_median,tmcc_deviation,sif_mean,sif_median,sif_deviation,if_mean,lif_median,lif_deviation	leaf_counters=mmcc,tmcc,sif,lif
rrd_view_put	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/analytic/rrd/view	-prune=-path "*" -type d
analytic	PUT	api.pmccabe_collector.restapi.org/project/{uuid}/analytic	--start=1701154260	--step=1	NO_NAME_PARAM.0=DS:mmcc:GAUGE:1y:U:U	NO_NAME_PARAM.1=DS:tmcc:GAUGE:1y:U:U	NO_NAME_PARAM.2=DS:sif:GAUGE:1y:U:U	NO_NAME_PARAM.3=DS:lif:GAUGE:1y:U:U	NO_NAME_PARAM.4=DS:mmcc_median:GAUGE:1y:U:U	NO_NAME_PARAM.5=DS:tmcc_median:GAUGE:1y:U:U	NO_NAME_PARAM.6=DS:sif_median:GAUGE:1y:U:U	NO_NAME_PARAM.7=DS:lif_median:GAUGE:1y:U:U	NO_NAME_PARAM.8=DS:mmcc_deviation:GAUGE:1y:U:U	NO_NAME_PARAM.9=DS:tmcc_deviation:GAUGE:1y:U:U	NO_NAME_PARAM.10=DS:sif_deviation:GAUGE:1y:U:U	NO_NAME_PARAM.11=DS:lif_deviation:GAUGE:1y:U:U	NO_NAME_PARAM.12=RRA:LAST:0.1:1:10000
rrd	POST	api.pmccabe_collector.restapi.org/project/{uuid}/analytic/rrd	--no-overwrite=	-method=update
view	GET	api.pmccabe_collector.restapi.org/project/{uuid}/statistic/view	-attr=mmcc,tmcc,sif,lif
