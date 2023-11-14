#!/usr/bin/bash

shopt -s extglob
. /package/setenv.sh

inotifywait -m ${1} -e create -e moved_to -e delete -e moved_from --include '(\.patch)|(\.xml)|(\.svg)' |
    while read dir action file; do
        case "$action" in
            CREATE|MOVED_TO )
                case "$file" in
                    @(*.patch) )
                        ;;
                    *)
                        ;;
                esac
                ;;
            DELETE|MOVED_FROM)
                case $file in
                    @(${REPO_BRANCH}.svg)|@(${REPO_BRANCH}.xml) )
                        echo "recalculate data for whole repository"
                            ${WORK_DIR}/update_existing_repo.sh ${REPO_BRANCH}
                            ${WORK_DIR}/build_pmccabe_xml.sh "${REPO_BRANCH}.xml"
                            ${WORK_DIR}/build_pmccabe_flamegraph.sh "${REPO_BRANCH}.xml" "${REPO_BRANCH}.svg"
                        ;;
                    *)
                        ;;
                esac
                ;;
            *)
            ;;
        esac

    done
