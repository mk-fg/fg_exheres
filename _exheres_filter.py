#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import os, sys, re
action, path = sys.argv[1:]
if not re.match(r'^packages/([^/]+)/([^/]+)/([^/]+).exheres-0$', path):
	sys.stdout.write(sys.stdin.read())
	sys.exit()

import itertools as it, operator as op, functools as ft

import codecs
sys.stdin = codecs.getreader('utf-8')(sys.stdin)
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

mod = __import__('_hook_pre-commit')
src, chk = it.tee(sys.stdin, 2)

def filter_base(src, src_seq, dst_seq):
	src_seq_len = len(src_seq)
	for line in src:
		indent = ''
		while line.startswith(src_seq):
			indent, line = dst_seq+indent, line[src_seq_len:]
		sys.stdout.write(indent + line)

filter_clean = ft.partial(filter_base, src_seq='\t', dst_seq=' '*4)
filter_smudge = ft.partial(filter_base, src_seq=' '*4, dst_seq='\t')

if action == 'clean':
	mod.err_count = 0
	mod.check_file(chk, os.path.basename(path))
	filter_clean(src)
	with mod.checker_db() as cdb:
		cdb[path] = mod.err_count
	if mod.err_count:
		print('File: {}'.format(path), file=sys.stderr)
		sys.exit(1)

elif action == 'smudge':
	filter_smudge(src)

else:
	raise ValueError('Unsupported action: {}'.format(action))
