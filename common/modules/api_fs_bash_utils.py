def __exec_watchdog_function__():
    function_name = "exec_watchdog"
    return function_name, [
        "{}() ".format(function_name) + " {\n",
        "    local WATCH_PID=${1}\n",
        "    local OUT_PIPE=${2}\n",
        "    if [ -z ${WATCH_PID} ]; then\n",
        "        return\n",
        "    fi\n",
        "    if [ ${WATCH_PID} != 0 ]; then\n",
        "        # check if a WATCHDOG child-process is alive\n",
        "        kill -s 0 ${WATCH_PID} > /dev/null 2>&1\n",
        "        local WATCHDOG_RESULT=$?\n",
        "        if [ $WATCHDOG_RESULT == 0 ]; then\n",
        "            #its alive: nobody has read ${OUT_PIPE} yet. Initiate reading intentionally\n",
        "            timeout 2 /bin/bash -c \"cat ${OUT_PIPE} > /dev/null 2>&1\"\n",
        '            if [ $? == 124 ] ; then echo "`date +%H:%M:%S:%3N`\t`hostname`\tRESET:\t${OUT_PIPE}"; fi\n',
        "        fi\n",
        "        # avoid zombie\n",
        "        wait ${WATCH_PID}\n",
        "    fi\n",
        "}\n",
    ]

def generate_exec_watchdog_function():
    return __exec_watchdog_function__()[1]

def exec_watchdog_function():
    return __exec_watchdog_function__()[0]




def __extract_attr_value_from_string_function__():
    function_name = "extract_avp_from_string_or_default"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    local ATTR="${1}"\n',
        '    local STR="${2}"\n',
        '    local DEFAULT="${3}"\n',
        '    local AVP_DELIM="${4}"\n',
        '    local VALUE=\n',
        '    readarray -t IN_SERVER_REQUEST_ARGS <<< "${STR}"\n',
        "    for arg in ${IN_SERVER_REQUEST_ARGS[@]}\n",
        "    do\n",
        '        if [[ "${arg}" = "${ATTR}${AVP_DELIM}"* ]];\n',
        "        then\n",
        '            readarray -d ${AVP_DELIM} -t AVP <<< "${arg}"\n',
        "            VALUE=${AVP[1]}\n",
        #            stop on first value
        "            break\n",
        "        fi\n",
        "    done\n",
        "    if [ -z ${VALUE} ]; then\n",
        "        VALUE=${DEFAULT}\n",
        "    fi\n",
        "    VALUE=$(echo $VALUE|tr -d '\\n')\n",
        r"    eval $5='" +'"${VALUE}"' + "'\n",
        "}\n"
    ]

def generate_extract_attr_value_from_string():
    return __extract_attr_value_from_string_function__()[1]

def extract_attr_value_from_string():
    return __extract_attr_value_from_string_function__()[0]



def __add_suffix_if_exist_function__():
    function_name = "add_suffix_if_exist"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '   local SUFFIX=${1}\n',
        '   local STR_TO_UPDATE=${2}\n',
        '   local OUT=${2}\n',
        '   if [ -z ${OUT} ]; then echo "OUT is empty. Termination"; kill -SIGHUP $$; fi\n',
        '   if [ ! -z ${SUFFIX} ]; then OUT="${STR_TO_UPDATE}_${SUFFIX}"; fi\n',
        r"   eval $3='" +'"${OUT}"' + "'\n",
        "}\n"
        ]

def generate_add_suffix_if_exist():
    return __add_suffix_if_exist_function__()[1]

def add_suffix_if_exist():
    return __add_suffix_if_exist_function__()[0]



def __wait_until_pipe_exist_function__():
    function_name = "wait_until_pipe_exist"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    while [ ! -p ${1} ]; do sleep 0.1; done\n',
        '}\n'
        ]

def generate_wait_until_pipe_exist():
    return __wait_until_pipe_exist_function__()[1]

def wait_until_pipe_exist():
    return __wait_until_pipe_exist_function__()[0]


def __unblock_query_pipe_writers_by_owner_function__():
    function_name = "unblock_query_pipe_writers_by_owner"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    local pipe_in=${1}\n',
        '    local sanitize_timeout=${2}\n',
        '    if [ -z ${sanitize_timeout} ]; then\n',
        '       sanitize_timeout=2\n',
        '    fi\n',
        '    if [ ! -p ${pipe_in} ]; then\n',
        "       echo \"Nothing to unblock: ${pipe_in} doesn't exist\"\n",
        '       return\n',
        '    fi\n',
        '    local temporary_pipe_in=${1}`date +%H%M%S`\n',
        '    ln ${pipe_in} ${temporary_pipe_in}\n',
        '    rm -f ${pipe_in}\n',
        '    NEED_UNBLOCK=true\n',
        '    let waiting_session=0\n',
        '    while ${NEED_UNBLOCK}\n',
        '    do\n',
        '        timeout ${sanitize_timeout} /bin/bash -c "cat ${temporary_pipe_in} > /dev/null 2>&1"\n',
        '        local res=$?\n',
        '        if [ $res == 124 ]; then\n',
        '            NEED_UNBLOCK=false\n',
        '            break\n',
        '        fi\n',
        '        let waiting_session=${waiting_session}+1\n',
        '    done\n',
        '    if [ $waiting_session -ne 0 ]; then\n',
        '        echo "Unblocked sessions on: ${pipe_in}, count: ${waiting_session}"\n',
        '    fi\n',
        '    rm -f ${temporary_pipe_in}\n',
        '}\n'
        ]

def generate_unblock_query_pipe_writers_by_owner():
    return __unblock_query_pipe_writers_by_owner_function__()[1]

def unblock_query_pipe_writers_by_owner():
    return __unblock_query_pipe_writers_by_owner_function__()[0]

def __unblock_result_pipe_readers_by_owner_function__():
    function_name = "unblock_result_pipe_readers_by_owner"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    local pipe_out=${1}\n',
        '    local sanitize_timeout=${2}\n',
        '    if [ -z ${sanitize_timeout} ]; then\n',
        '       sanitize_timeout=1\n',
        '    fi\n',
        '    if [ ! -p ${pipe_out} ]; then\n',
        "       echo \"Nothing to unblock: ${pipe_out} doesn't exist\"\n",
        '       return\n',
        '    fi\n',
        '    local temporary_pipe_out=${1}`date +%H%M%S`\n',
        '    ln ${pipe_out} ${temporary_pipe_out}\n',
        '    rm -f ${pipe_out}\n',
        '    NEED_UNBLOCK=true\n',
        '    let waiting_session=0\n',
        '    while ${NEED_UNBLOCK}\n',
        '    do\n',
        '        timeout ${sanitize_timeout} /bin/bash -c "echo > ${temporary_pipe_out} > /dev/null 2>&1"\n',
        '        local res=$?\n',
        '        if [ $res == 124 ]; then\n',
        '            NEED_UNBLOCK=false\n',
        '            break\n',
        '        fi\n',
        '        let waiting_session=${waiting_session}+1\n',
        '    done\n',
        '    if [ $waiting_session -ne 0 ]; then\n',
        '        echo "Unblocked sessions on: ${pipe_out}, count: ${waiting_session}"\n',
        '    fi\n',
        '    rm -f ${temporary_pipe_out}\n',
        '}\n'
        ]

def generate_unblock_result_pipe_reader_by_owner():
    return __unblock_result_pipe_readers_by_owner_function__()[1]

def unblock_result_pipe_readers_by_owner():
    return __unblock_result_pipe_readers_by_owner_function__()[0]


def __unblock_readers_of_result_pipe_array_by_owner_function__():
    function_name = "unblock_readers_of_result_pipe_array_by_owner"
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    local pipe_out=${1}\n',
        '    local sanitize_timeout=${2}\n',
        '    if [ -z ${sanitize_timeout} ]; then\n',
        '       sanitize_timeout=1\n',
        '    fi\n',
        '    for p in ${pipe_out}; do\n',
        '        ' + unblock_result_pipe_readers_by_owner() + " ${p} ${sanitize_timeout}\n",
        '    done\n',
        '}\n'
        ]

def generate_unblock_readers_of_result_pipe_array_by_owner():
    return __unblock_readers_of_result_pipe_array_by_owner_function__()[1]

def unblock_readers_of_result_pipe_array_by_owner():
    return __unblock_readers_of_result_pipe_array_by_owner_function__()[0]
