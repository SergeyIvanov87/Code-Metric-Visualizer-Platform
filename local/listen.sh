#!/usr/bin/bash

shopt -s extglob
. /package/setenv.sh

inotifywait -m ${1} -e create -e moved_to --include '(\.wingman_get_fl)|(\.wingman_get_xml)' |
    while read dir action file; do
        echo "file: ${file}, action; ${action}, dir: ${dir}"
        case "$action" in
            CREATE|MOVED_TO|MODIFY )
                case "$file" in
                    @(*.wingman_get_fl) )
                        ${WORK_DIR}/build_pmccabe_xml.sh "${SHARED_DIR}/${file}.xml"
                        ${WORK_DIR}/build_pmccabe_flamegraph.sh "${SHARED_DIR}/${file}.xml" "${SHARED_DIR}/${file}.svg"
                        ;;
                    *)
                        ;;
                esac
                ;;
            *)
            ;;
        esac

    done
