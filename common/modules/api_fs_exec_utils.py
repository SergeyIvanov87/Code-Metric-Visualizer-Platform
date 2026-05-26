#!/usr/bin/python

from api_fs_bash_utils import (
    split_quoted_arguments,
    generate_split_quoted_arguments
)

"""
Provides utilities to generate API executor scripts
"""

def generate_exec_header():
    return [ r"#!/bin/bash",
             r"",
             *generate_split_quoted_arguments()
           ]

def generate_get_result_type(extension):
    return [ r'if [[ ${1} == "--result_type" ]];',
             r"then",
             f'    echo "{extension}"',
             r"    exit 0",
             r"fi"
    ]

def generate_api_node_env_init():
    return [ r'if [ "$#" -ne 2 ]; then',
             r'    echo "Illegal number of parameters $#. Expected parameters: API_NODE and IN_SERVER_REQUEST_ARGS array"',
             r'    exit -1',
             r'fi',
             r'API_NODE="${1}"',
             r'INPUT_ARGUMENT_STRING="${2}"',
             r'declare -a IN_SERVER_REQUEST_ARGS=()',
             r'declare -a OVERRIDEN_CMD_ARGS=()',
             r'if ! ' + split_quoted_arguments() + ' "${INPUT_ARGUMENT_STRING}" IN_SERVER_REQUEST_ARGS',
             r'then',
             r'  printf "Cannot parse arguments from: ${INPUT_ARGUMENT_STRING}" >&2',
             r'  exit -1',
             r'fi',
             r''
    ]

def generate_read_api_fs_args():
    return [ r'for entry in "${API_NODE}"/*.*',
             r"do",
             r"    ",
             r'    file_basename="${entry##*/}"',
             r'    param_name="${file_basename#*.}"',
             r'    special_kind_param_name="${param_name%.*}"',
             r'    value_from_input=0',
             r'    ',
             r'    readarray -t arr < "${entry}"',
             r'    ',
             r'    # readarray -t removes line terminators. For a genuinely multiline file',
             r'    # read the complete content into one scalar so embedded and trailing',
             r'    # newline characters remain in one command-line argument.',
             "    IFS= read -r -d '' file_value < \"${entry}\" || true",
             "    file_value_without_final_newline=\"${file_value%$'\n'}\"",
             "    if [[ \"${file_value_without_final_newline}\" == *$'\\n'* ]]; then",
             r'        arr=("${file_value}")',
             r'    fi',
             r'    if [[ "${special_kind_param_name}" != "NO_NAME_PARAM" ]];',
             r"    then",
             r'        OVERRIDEN_CMD_ARGS+=("${param_name}")',
             r'        for arg in "${IN_SERVER_REQUEST_ARGS[@]}"',
             r"        do",
             r'            if [[ "${arg}" = *"${param_name}="* ]];',
             r"            then",
             r'                # Split only at the first \'=\'',
             r'                value="${arg#"${param_name}="}"',
             r'                # Preserve the complete value as one array element,',
             r'                # including spaces and additional \'=\' characters.',
             r'                arr=("${value}")',
             r'                value_from_input=1',
             r'                break',
             r"            fi",
             r"        done",
             r"    fi",
             r'    for a in "${arr[@]}"',
             r"    do",
             "        if ((value_from_input)) || [[ \"${a}\" == \\\"* || \"${a}\" == *$'\\n'* ]];",
             r"        then",
             r'            OVERRIDEN_CMD_ARGS+=("${a}")',
             r"        else",
             r"            # Preserve the legacy behavior where an unquoted file line",
             r"            # can contain multiple whitespace-separated arguments.",
             r'            read -r -a line_arguments <<< "${a}"',
             r'            OVERRIDEN_CMD_ARGS+=("${line_arguments[@]}")',
             r"        fi",
             r"    done",
             r"done"
    ]

def generate_bypassed_params_formatting():
    return [ r'replace_space_in_even_position() {',
             r'    local output_string=""',
             r'    local let space_counter=0',
             r'    local str="${1}"',
             r'    for (( i=0; i<${#str}; i++ )); do',
             r'        local symbol="${str:$i:1}"',
             r'        if [ " " == "${symbol}" ]',
             r'        then',
             r'            if [ "$(( $space_counter % 2 ))" -eq 0 ]; then',
             r'                symbol="="',
             r'            fi',
             r'            let space_counter=$space_counter+1',
             r'        fi',
             r'        output_string="${output_string}${symbol}"',
             r'    done',
             r'    echo "${output_string}"',
             r'}'
    ]
