#!/usr/bin/python

"""
Provides utilities to generate API executor scripts
"""

def generate_exec_header():
    return [ r"#!/usr/bin/bash" ]

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



'''
#!/usr/bin/bash

if [[ ${1} == "--result_type" ]];
then
    echo ""
    exit 0
fi
API_NODE=${2}
readarray -t IN_ARGS <<< "${3}"
SUBSTITUTE_OUTPUT=0
. ${1}/setenv.sh

for entry in "${API_NODE}"/*.*
do
    file_basename=${entry##*/}
    param_name=${file_basename#*.}
    readarray -t arr < ${entry}
    special_kind_param_name=${param_name%.*}
    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];
    then
        brr+=(${param_name})
        if [[ "${3}" = *${param_name}* ]];
        then
             echo "match! ${param_name}"
             SUBSTITUTE_OUTPUT=1
        fi

    fi
    for a in ${arr[@]}
    do
        if [[ ${a} == \"* ]];
        then
            brr+=("${a}")
        else
            brr+=(${a})
        fi
    done
done

if [ ${SUBSTITUTE_OUTPUT} == 1 ]
then
    echo "${3}"
else
    echo "${brr[@]}"
fi
exit 0
echo -e '\n\n\n'
for b in ${brr[@]}
do
   echo "fs item: ${b}"
done

for a in ${IN_ARGS[@]}
do
   echo "arg item: ${a}"
done
#echo "${IN_ARGS[@]}"
'''

'''
SUBSTITUTE!!!
#!/usr/bin/bash

if [[ ${1} == "--result_type" ]];
then
    echo ""
    exit 0
fi
API_NODE=${2}
readarray -t IN_ARGS <<< "${3}"
SUBSTITUTED_ARG=""
. ${1}/setenv.sh

for entry in "${API_NODE}"/*.*
do
    file_basename=${entry##*/}
    param_name=${file_basename#*.}
    readarray -t arr < ${entry}
    special_kind_param_name=${param_name%.*}
    if [[ ${special_kind_param_name} != 'NO_NAME_PARAM' ]];
    then
        brr+=(${param_name})
        for arg in ${IN_ARGS[@]}
        do
           if [[ "${arg}" = *${param_name}* ]];
           then
             readarray -d '=' -t ARG_ARR <<< "${arg}"
             readarray -t arr <<< "${ARG_ARR[1]}"
           fi
        done
    fi
    for a in ${arr[@]}
    do
        if [[ ${a} == \"* ]];
        then
            brr+=("${a}")
        else
            brr+=(${a})
        fi
    done
done

#if [ ${SUBSTITUTE_OUTPUT} == 1 ]
#then
#    echo "${3}"
#else
    echo "${brr[@]}"
#fi
exit 0
echo -e '\n\n\n'
for b in ${brr[@]}
do
   echo "fs item: ${b}"
done

for a in ${IN_ARGS[@]}
do
   echo "arg item: ${a}"
done
#echo "${IN_ARGS[@]}"
'''
