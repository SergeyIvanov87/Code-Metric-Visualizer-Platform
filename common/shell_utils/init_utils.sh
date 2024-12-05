#!/bin/bash


get_unavailable_services() {
    API_DEPS_PATH=${1}
    let wait_dependencies_counter=0
    let wait_dependencies_counter_limit=30
    let wait_dependencies_sec=1
    ANY_SERVICE_UNAVAILABLE=1
    while :
    do
        ANY_SERVICE_UNAVAILABLE=
        for deps_service in ${API_DEPS_PATH}/*; do
            if [ -d ${deps_service} ]; then
                MISSING_API_QUERIES=`${3} ${deps_service}`
                if [ ! -z "${MISSING_API_QUERIES}" ]; then
                    echo "The service \"${deps_service}\" is unavailable using this API:"
                    echo "${MISSING_API_QUERIES}"
                    let ANY_SERVICE_UNAVAILABLE=${ANY_SERVICE_UNAVAILABLE}+1
                fi
            fi
        done
        if [ -z ${ANY_SERVICE_UNAVAILABLE} ]; then
            break
        fi
        if [ ${wait_dependencies_counter} == ${wait_dependencies_counter_limit} ]; then
            eval ${2}=$ANY_SERVICE_UNAVAILABLE
            break
        fi
        let wait_dependencies_counter=$wait_dependencies_counter+1
        echo "WARNING: One or more services are offline. Another attempt: ${wait_dependencies_counter}/${wait_dependencies_counter_limit} - will be made in ${wait_dependencies_sec} seconds."
        sleep ${wait_dependencies_sec} &
        wait $!
    done

}
