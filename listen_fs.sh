#!/usr/bin/bash

inotifywait -m ${1} -e create -e moved_to --include '\.patch' |
    while read dir action file; do
        echo "The file '$file' appeared in directory '$dir' via '$action'"
        # do something with the file
    done
