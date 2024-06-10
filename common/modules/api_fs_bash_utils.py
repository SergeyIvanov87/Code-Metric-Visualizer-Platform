def generate_exec_watchdog_function():
    function_name = "exec_watchdog"
    return function_name, [
        "{}() ".format(function_name) + " {\n",
        "    WATCH_PID=${1}\n",
        "    OUT_PIPE=${2}\n",
        "    if [ -z ${WATCH_PID} ]; then\n",
        "        return\n",
        "    fi\n",
        "    if [ ${WATCH_PID} != 0 ]; then\n",
        "        # check if a WATCHDOG child-process is alive\n",
        "        kill -s 0 ${WATCH_PID} > /dev/null 2>&1\n",
        "        WATCHDOG_RESULT=$?\n",
        "        if [ $WATCHDOG_RESULT == 0 ]; then\n",
        "            #its alive: nobody has read ${OUT_PIPE} yet. Initiate reading intentionally\n",
        "            timeout 2 cat ${OUT_PIPE} > /dev/null 2>&1\n",
        "        fi\n",
        "        # avoid zombie\n",
        "        wait ${WATCH_PID}\n",
        "    fi\n",
        "}\n",
    ]


def generate_extract_attr_value_from_string():
    function_name = "extract_avp_from_string_or_default"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    ATTR="${1}"\n',
        '    STR="${2}"\n',
        '    DEFAULT="${3}"\n',
        '    AVP_DELIM="${4}"\n',
        '    readarray -t IN_ARGS <<< "${STR}"\n',
        "    for arg in ${IN_ARGS[@]}\n",
        "    do\n",
        '        if [[ "${arg}" = ${ATTR}* ]];\n' "    then\n",
        '            readarray -d ${AVP_DELIM} -t AVP <<< "${arg}"\n',
        "            VALUE=${AVP[1]}\n",
        "        fi\n",
        "    done\n",
        "    if [ -z ${VALUE} ]; then\n",
        "        VALUE=${DEFAULT}\n",
        "    fi\n",
        "    VALUE=$(echo $VALUE|tr -d '\n')\n",
        "    eval $5='$VALUE'\n",
        "}\n"
    ]

def add_suffix_if_exist():
    function_name = "add_suffix_if_exist"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '   SUFFIX=${1}\n',
        '   STR_TO_UPDATE=${2}\n',
        '   OUT=${2}\n',
        '   if [ ! -z ${SUFFIX} ]; then OUT="${STR_TO_UPDATE}_${SUFFIX}"; fi\n',
        "   eval ${3}='$OUT'\n",
        "}\n"
        ]

def wait_until_pipe_exist():
    function_name = "wait_until_pipe_exist"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    while [ ! -p ${1} ]; do sleep 0.1; done\n',
        '}\n'
        ]
