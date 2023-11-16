#!/usr/bin/bash

shopt -s extglob
. /package/setenv.sh

inotifywait -m ${1} -e create -e moved_to -e delete -e moved_from --include '(\.patch)|(\.xml)|(\.svg)' |
    while read dir action file; do
        echo "file: ${file}, action; ${action}, dir: ${dir}"
        case "$action" in
            CREATE|MOVED_TO|MODIFY )
                case "$file" in
                    @(*.patch) )
                        ${WORK_DIR}/apply_patch_in_repo.sh ${file}
                        ${WORK_DIR}/build_pmccabe_xml.sh "${file}.xml"
                        ${WORK_DIR}/build_pmccabe_flamegraph.sh "${file}.xml" "${file}.svg"
                        ${WORK_DIR}/reset_existing_repo.sh ${REPO_BRANCH}
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
