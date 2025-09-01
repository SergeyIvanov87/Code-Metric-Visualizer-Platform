#!/usr/bin/python

"""
Provides utilities to generate API executor scripts
"""

def generate_exec_header():
    return [ r"#!/bin/bash" ]

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
             r"API_NODE=${1}",
             r'readarray -t IN_SERVER_REQUEST_ARGS <<< "${2}"'
    ]

def generate_read_api_fs_args():
    return [ r'for entry in "${API_NODE}"/*.*',
             r"do",
             r"    if [[ $entry == *.md ]]; then continue; fi",
             r"    ",
             r"    file_basename=${entry##*/}",
             r"    param_name=${file_basename#*.}",
             r"    readarray -t arr < ${entry}",
             r"    special_kind_param_name=${param_name%.*}",
             r"    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];",
             r"    then",
             r"        OVERRIDEN_CMD_ARGS+=(${param_name})",
             r"        for arg in ${IN_SERVER_REQUEST_ARGS[@]}",
             r"        do",
             r'            if [[ "${arg}" = *"${param_name}="* ]];',
             r"            then",
             r'''                readarray -d '=' -t ARG_ARR <<< "${arg}"''',
             r'                readarray -t arr <<< "${ARG_ARR[1]}"',
             r"            fi",
             r"        done",
             r"    fi",
             r"    for a in ${arr[@]}",
             r"    do",
             r"        if [[ ${a} == \"* ]];",
             r"        then",
             r'            OVERRIDEN_CMD_ARGS+=("${a}")',
             r"        else",
             r"            OVERRIDEN_CMD_ARGS+=(${a})",
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
