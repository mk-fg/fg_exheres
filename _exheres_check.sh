#!/bin/bash
find packages -name '*.exheres-0' |
	GIT_DIR=.git xargs -n1 '-I{}' /bin/sh -c "./_exheres_filter.py clean {} <{} >/dev/null"
