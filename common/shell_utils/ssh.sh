#!/bin/bash

wait_for_ssh() {
    # $1 - user
    # $2 - host
    # $3 - pwd
    while ! sshpass -p "$3" ssh -o StrictHostKeyChecking=no ${1}@${2} uname -a ; do sleep 1; done
}

execute_ssh_cmd() {
    # $1 - user
    # $2 - host
    # $3 - pwd
    # $4 - cmd
    sshpass -p "${3}" ssh -o StrictHostKeyChecking=no ${1}@${2} '${4}'
}

scp_copy_file() {
    # $1 - source
    # $2 - dst
    # $3 - pwd
    sshpass -p "${3}" scp ${source} ${dst} #root@syslog-ng:/config/patch_opt_in
}
