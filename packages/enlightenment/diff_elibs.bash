#!/bin/bash

dst=/tmp/e_config_diffs

usage() {
	echo >&2 "Usage: $0 [-n] ver"
	echo >&2 "Example: $0 1.7.5"
	echo >&2
	echo >&2 "Script to diff 'configure --help' outputs of elibs"
	echo >&2 " to detect option changes between different versions."
	echo >&2 "Has to be run with one version first, then the other to show the diffs."
	echo >&2 "-n option only runs diff if there are files to do that with."
	echo >&2 "Aforementioned outputs are stored in: ${dst}"
	exit $1
}

diff_only=
[[ "$1" = -n ]] && { diff_only=true; shift; }

[[ $# -ne 1 ]] && usage 1
cd "$(dirname "$0")"

mkdir -p "$dst"

diff=colordiff
which $diff >/dev/null 2>&1 || diff=diff

for p in $(
	find -type f -name "*-$1.exheres-0" |
	awk 'match($0, /^\.\/([^\/]+)\/.*$/, a) {print a[1]}' )
do

	[[ -z "$diff_only" ]] && {
		echo "Resolving package: $p"
		cave resolve -zx1 "enlightenment/${p}[~${1}]"\
			--abort-at-phase configure >/dev/null 2>&1
		configure=( /var/tmp/paludis/build/enlightenment-$p-$1/work/*/configure )
		[[ "${#configure[@]}" -ne 1 ]] && {
			echo >&2 "Failed to find build-path for package: $p-$1 (matches: ${configure[@]})"; exit 1; }
		configure=${configure[0]}

		pushd "$(dirname "$configure")" >/dev/null
		./configure --help > "${dst}/${p}-${1}.help"
		popd >/dev/null
	}

	helps=( ${dst}/${p}-*.help )
	[[ "${#helps[@]}" -ge 2 ]] && {
		echo -e "  -----== Diffs for package: $p\n"
		hf_src=
		for hf in "${helps[@]}"; do
			[[ -n "$hf_src" ]] && $diff -uw "$hf_src" "$hf"
			hf_src=$hf
		done
	}

done
