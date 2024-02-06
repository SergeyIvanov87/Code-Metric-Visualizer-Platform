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
    return [ r"API_NODE=${2}",
             r'readarray -t IN_ARGS <<< "${3}"',
             r". ${1}/setenv.sh"
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
             r"        brr+=(${param_name})",
             r"        for arg in ${IN_ARGS[@]}",
             r"        do",
             r'            if [[ "${arg}" = *${param_name}* ]];',
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
             r'            brr+=("${a}")',
             r"        else",
             r"            brr+=(${a})",
             r"        fi",
             r"    done",
             r"done"
    ]

def generate_bypassed_params_formatting():
    return [ r'replace_space_in_even_position() {',
             r'    output_string=""',
             r'    let space_counter=0',
             r'    str="${1}"',
             r'    for (( i=0; i<${#str}; i++ )); do',
             r'        symbol="${str:$i:1}"',
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
