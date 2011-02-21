#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

####################

tmp_optz = '/etc/paludis/options.conf.d/check_emptydirs.conf'

####################


import argparse
parser = argparse.ArgumentParser(
	description='Tool to check empty dirs, present in any flag combo for a given package.')
parser.add_argument('--debug', action='store_true', help='Verbose operation mode.')
parser.add_argument('--debug-cave', action='store_true', help='Do not supress cave output.')
parser.add_argument('pkg', help='Package spec.')
parser.add_argument('flags', nargs='+', help='Flags to check.')
argz = parser.parse_args()

if '/' not in argz.pkg:
	parser.error('Package spec should include category')


import itertools as it, operator as op, functools as ft
from subprocess import Popen, PIPE, STDOUT
from glob import glob
import os, sys


def test_combos(pkg, flags):
	flags = set(flags)
	combos = set(it.chain.from_iterable(
		it.imap(frozenset, it.combinations(flags, c))
		for c in xrange(len(flags)) ))

	log.debug( 'Found (enabled) flag combos ({}): {}'\
		.format(len(combos), ', '.join(str(list(c)) for c in combos)) )

	for combo in combos:
		combo = list(it.imap('-{}'.format, flags-combo)) + list(combo)
		open(tmp_optz, 'w').write('{} -* {}\n'.format(pkg, ' '.join(combo)))
		log.debug('Testing flag combo: {}'.format(combo))

		cave = ['cave', 'resolve', '-zx1', pkg, '--abort-at-phase', 'merge']
		log.debug('Cave command: {}'.format(' '.join(cave)))
		Popen(cave, **cave_out).wait()

		try: image, = glob('/var/tmp/paludis/build/{}-*/image/'.format(pkg.split(':', 1)[0].replace('/', '-')))
		except (ValueError, IndexError):
			log.error('Failed to find IMAGE path (combo: {})'.format(combo))
			continue

		proc = Popen(['find', '.', '-type', 'd', '-empty'], cwd=image, stdout=PIPE)
		empty_dirs = map(op.methodcaller('strip'), proc.stdout)
		proc.wait()

		log.info( '\n - Package: {}\n - Flags: {}\n - Empty_dirs:\n{}'\
			.format(pkg, ' '.join(combo), ''.join('  {}\n'.format(d[2:]) for d in empty_dirs)) )


cave_out = dict(stdout=open('/dev/null', 'w'), stderr=STDOUT)\
	if not argz.debug_cave else dict()

import logging
logging.basicConfig(level=logging.DEBUG if argz.debug else logging.INFO)
log = logging.getLogger()

try: test_combos(argz.pkg, argz.flags)
finally:
	if os.path.exists(tmp_optz): os.unlink(tmp_optz)
