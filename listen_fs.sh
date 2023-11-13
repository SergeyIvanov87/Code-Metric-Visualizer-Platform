#!/usr/bin/bash

. /package/setenv.sh

inotifywait -m ${1} -e create -e moved_to -e delete -e moved_from --include '(\.patch)|(\.xml)|(\.svg)' |
    while read dir action file; do
        echo "The file '$file' appeared in directory '$dir' via '$action'"
        # do something with the file
		
    done
