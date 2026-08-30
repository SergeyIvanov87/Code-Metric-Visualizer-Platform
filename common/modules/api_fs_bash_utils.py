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

def __split_quoted_arguments_function__(override_function_name):
    function_name = "split_quoted_arguments" if not override_function_name else override_function_name
    # Split a string on unquoted whitespace.
    #
    # Unquoted spaces separate arguments:
    #
    #   A=one B=two
    #       -> A=one
    #       -> B=two
    #
    # Multiple unquoted whitespace characters are treated as separators:
    #
    #   A=one     B=two
    #       -> A=one
    #       -> B=two
    #
    # Tabs and newlines also separate unquoted arguments:
    #
    #   A=one
    #   B=two
    #       -> A=one
    #       -> B=two
    #
    # Double quotes preserve spaces in a value.
    # The grouping quotation marks are removed:
    #
    #   A="one two" B=three
    #       -> A=one two
    #       -> B=three
    #
    # Double quotes preserve tabs and newlines:
    #
    #   A="one
    #   two" B=three
    #       -> A=one\ntwo
    #       -> B=three
    #
    # In the example above, \n represents a real newline character,
    # not the two literal characters '\' and 'n'.
    #
    # Additional '=' characters do not split an argument:
    #
    #   A=one=two B="x=y=z"
    #       -> A=one=two
    #       -> B=x=y=z
    #
    # Empty quoted values are supported:
    #
    #   A="" B=two
    #       -> A=
    #       -> B=two
    #
    # Quoted and unquoted parts of the same argument are concatenated:
    #
    #   A=one" two" B="x"y
    #       -> A=one two
    #       -> B=xy
    #
    # An entirely empty quoted argument is preserved:
    #
    #   A=one "" B=two
    #       -> A=one
    #       -> <empty argument>
    #       -> B=two
    #
    # Outside double quotes, backslash escapes the next character:
    #
    #   A=one\ two B=three
    #       -> A=one two
    #       -> B=three
    #
    # Outside double quotes, backslash can preserve a literal quote:
    #
    #   A=one\"two B=three
    #       -> A=one"two
    #       -> B=three
    #
    # Inside double quotes, \" produces a literal double quote:
    #
    #   A="one \"quoted\" value" B=three
    #       -> A=one "quoted" value
    #       -> B=three
    #
    # Inside double quotes, \\ produces one literal backslash:
    #
    #   A="one\\two" B=three
    #       -> A=one\two
    #       -> B=three
    #
    # In the result above, '\' is a literal backslash; '\t' is not
    # converted into a tab character.
    #
    # An ordinary backslash inside double quotes is preserved:
    #
    #   A="path\to\file" B=three
    #       -> A=path\to\file
    #       -> B=three
    #
    # A trailing backslash is preserved:
    #
    #   A=value\
    #       -> A=value\
    #
    # Shell-special characters are treated as ordinary data. They are
    # not expanded or executed by this parser:
    #
    #   A='$HOME;*.txt' B="x&y|z" C="a(b)"
    #       -> A='$HOME;*.txt'
    #       -> B=x&y|z
    #       -> C=a(b)
    #
    # Note: single quotes have no grouping meaning to this parser.
    # They are treated as literal characters. Use double quotes when
    # a value contains whitespace.
    #
    # An unmatched double quote is an error:
    #
    #   A="one two
    #       -> error: Unterminated double quote in argument string
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
        '                # Within quotes, keep ordinary backslashes literal. A\n',
        '                # backslash only escapes a quote or another backslash.\n',
        '                if ((in_quotes)); then\n',
        '                    if ((i + 1 < ${#input})) &&\n',
        '                       [[ "${input:i+1:1}" == \'"\' || "${input:i+1:1}" == \'\\\\\' ]]; then\n',
        '                         escaped=1\n',
        '                    else\n',
        "                       current+='\'\n",
        '                    fi\n',
        '                else\n',
        '                    escaped=1\n',
        '                fi\n',
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

def generate_split_quoted_arguments(override_function_name = "split_quoted_arguments"):
    return __split_quoted_arguments_function__(override_function_name)[1]

def split_quoted_arguments(override_function_name = "split_quoted_arguments"):
    return __split_quoted_arguments_function__(override_function_name)[0]


def __extract_attr_value_from_string_using_tokenizer_function__():
    function_name = "extract_avp_from_string_or_default"
    return function_name, [
        *generate_split_quoted_arguments("split_quoted_arguments_inner"), r"",
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
        '    if ! ' + split_quoted_arguments("split_quoted_arguments_inner") + ' "${str}" args; then\n',
        '        printf "Cannot split arguments: ${str} into args" >&2\n',
        '        return 1\n',
        '    fi\n',
        '    for arg in "${args[@]}"; do\n',
        '      if [[ "${arg}" == "${attr}${delimiter}"* ]]; then\n',
        '        # Remove only the first "attribute+delimiter" prefix.\n',
        '        value="${arg#"${attr}${delimiter}"}"\n',
        '        break\n',
        '      fi\n',
        '    done\n',
        '    if [[ -z "${value}" ]]; then\n',
        '       value="${default_value}"\n',
        '    fi\n',
        '    # Assign safely to the caller-specified variable.\n',
        '    printf -v "${output_name}" \'%s\' "${value}"\n',
        '}\n'
    ]



def generate_extract_attr_value_from_string():
    return __extract_attr_value_from_string_using_tokenizer_function__()[1]

def extract_attr_value_from_string():
    return __extract_attr_value_from_string_using_tokenizer_function__()[0]



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
