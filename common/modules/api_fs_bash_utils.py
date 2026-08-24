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
        '    local attr="${1}"\n',
        '    local str="${2}"\n',
        '    local default_value="${3}"\n',
        '    local delimiter="${4}"\n',
        '    local output_name="${5}"\n',
        '    local value=\n',
        '    local arg\n',
        '    local -a args\n',
        '    if [[ -z $delimiter ]]; then\n',
        '       printf "Delimiter cannot be empty\n" >&2\n',
        '       return 1\n',
        '    fi\n',
        '    # Split the input into whitespace-separated arguments.\n',
        '    read -r -a args <<< "$str"\n',
        '    for arg in "${args[@]}"; do\n',
        '    if [[ $arg == "${attr}${delimiter}"* ]]; then\n',
        '        # Remove only the first "attribute+delimiter" prefix.\n',
        '        value=${arg#"${attr}${delimiter}"}\n',
        '        break\n',
        '    fi\n',
        '    done\n',
        '    if [[ -z $value ]]; then\n',
        '       value=$default_value\n',
        '    fi\n',
        '    # Assign safely to the caller-specified variable.\n',
        '    printf -v "$output_name" \'%s\' "$value"\n',
        '}\n'
    ]

def __split_quoted_arguments_function__():
    function_name = "split_quoted_arguments"
    # Split a string on unquoted whitespace.
    #
    # Examples:
    #   A=one B=two
    #       -> A=one
    #       -> B=two
    #
    #   A="one two" B="x=y"
    #       -> A=one two
    #       -> B=x=y
    #
    return function_name, [
        "{}()".format(function_name) + " {\n",
        '    local input="${1}"\n',
        '    local output_name="${2}"\n',
        '    local -n output_ref="${output_name}"\n',
        '    local current=""\n',
        '    local character=""\n',
        '    local in_quotes=0\n',
        '    local escaped=0\n',
        '    local argument_started=0\n',
        '    local i\n',
        '    output_ref=()\n',
        '    for ((i = 0; i < ${#input}; i++)); do\n',
        '        character="${input:i:1}"\n',
        '        if ((escaped)); then\n',
        '            current+="${character}"\n',
        '            escaped=0\n',
        '            argument_started=1\n',
        '            continue\n',
        '        fi\n',
        '        case "${character}" in\n',
        '            \'\\\\\')\n',
        '                escaped=1\n',
        '                argument_started=1\n',
        '                ;;\n',
        '            \'"\')\n',
        '                if ((in_quotes)); then\n',
        '                    in_quotes=0\n',
        '                else\n',
        '                    in_quotes=1\n',
        '                fi\n',
        '\n',
        '                argument_started=1\n',
        '                ;;\n',
        '\n',
        '            \' \' | $\'\\t\' | $\'\\n\')\n',
        '                if ((in_quotes)); then\n',
        '                    current+="${character}"\n',
        '                elif ((argument_started)); then\n',
        '                    output_ref+=("${current}")\n',
        '                    current=""\n',
        '                    argument_started=0\n',
        '                fi\n',
        '                ;;\n',
        ' \n',
        '            *)\n',
        '                current+="${character}"\n',
        '                argument_started=1\n',
        '                ;;\n',
        '        esac\n',
        '    done\n',
        '\n',
        '    if ((escaped)); then\n',
        '        # Preserve a trailing backslash.\n',
        '        current+=\'\\\'\n',
        '    fi\n',
        '\n',
        '    if ((in_quotes)); then\n',
        '        printf "Unterminated double quote in argument string\\n" >&2\n',
        '        return 1\n',
        '    fi\n',
        '\n',
        '    if ((argument_started)); then\n',
        '        output_ref+=("${current}")\n',
        '    fi\n',
        '}\n'
    ]

def generate_split_quoted_arguments():
    return __split_quoted_arguments_function__()[1]

def split_quoted_arguments():
    return __split_quoted_arguments_function__()[0]


def __extract_attr_value_from_string_using_tokenizer_function__(need_generate_split_quoted_arg_func = True):
    function_name = "extract_avp_from_string_or_default_tokenized"
    return function_name, [
        *(generate_split_quoted_arguments() if need_generate_split_quoted_arg_func else []), r"",
        "{}()".format(function_name) + " {\n",
        '    local attr="${1}"\n',
        '    local str="${2}"\n',
        '    local default_value="${3}"\n',
        '    local delimiter="${4}"\n',
        '    local output_name="${5}"\n',
        '    local value=""\n',
        '    local arg\n',
        '    local -a args\n',
        '    if [[ -z "${delimiter}" ]]; then\n',
        '       printf "Delimiter cannot be empty\\n" >&2\n',
        '       return 1\n',
        '    fi\n',
        '    # Split the input into whitespace-separated arguments.\n',
        '    if ! ' + split_quoted_arguments() + ' "${str}" args; then\n',
        '        printf "Cannot split arguments: ${str} into args" >&2\n',
        '        return 1\n',
        '    fi\n',
        '    for arg in "${args[@]}"; do\n',
        '      if [[ "${arg}" == "${attr}${delimiter}"* ]]; then\n',
        '        # Remove only the first "attribute+delimiter" prefix.\n',
        '        value=${arg#"${attr}${delimiter}"}\n',
        '        break\n',
        '      fi\n',
        '    done\n',
        '    if [[ -z $value ]]; then\n',
        '       value="${default_value}"\n',
        '    fi\n',
        '    # Assign safely to the caller-specified variable.\n',
        '    printf -v "${output_name}" \'%s\' "${value}"\n',
        '}\n'
    ]



def generate_extract_attr_value_from_string():
    return __extract_attr_value_from_string_using_tokenizer_function__()[1]

def extract_attr_value_from_string(need_generate_helper_func = True):
    return __extract_attr_value_from_string_using_tokenizer_function__(need_generate_helper_func)[0]



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
