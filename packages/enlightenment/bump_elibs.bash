#!/bin/bash

usage() {
	echo >&2 "Usage: $0 ver_from ver_to"
	echo >&2 "Example: $0 1.7.2 1.7.4"
	exit $1
}

[[ $# -lt 2 ]] && usage 1

for p in $(find -type f -name "*-$1.exheres-0")
do git mv "$p" "${p/$1/$2}"
done
