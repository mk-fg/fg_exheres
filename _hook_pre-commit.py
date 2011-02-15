#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function


import itertools as it, operator as op, functools as ft
from datetime import datetime
import os, sys, re
from os.path import join, isfile

git_dir = os.environ['GIT_DIR']
base_dir = join(git_dir, '..')
print = ft.partial(print, file=sys.stderr)

def checker_db():
	import shelve, contextlib
	return contextlib.closing(
		shelve.open(join(git_dir, 'syntax_check')) )


err_count = 0
def signal_error(message):
	global err_count
	print(message)
	err_count += 1

class ChkException(Exception):
	def __init__(self, message, line=None):
		self.line = line
		super(ChkException, self).__init__(message)

def _build_stack(tb):
	while True:
		if not tb.tb_next: break
		tb = tb.tb_next
	stack = list()
	frame = tb.tb_frame
	while frame:
		stack.append(frame)
		frame = frame.f_back
	return reversed(stack)

def err_traceback(tb=None):
	message = ''
	if tb is None: tb = sys.exc_info()[2]
	err = list()
	for frame in _build_stack(tb):
		line = open(frame.f_code.co_filename).readlines()[frame.f_lineno - 1]
		if frame.f_code.co_name == 'safe_chk': continue # hide internals
		err.append('  {}: {!r}{}'.format( frame.f_code.co_name, line.strip(),
				',\n    line={!r}'.format(frame.f_locals['line']) if 'line' in frame.f_locals else '' ))
	return err

def chk_wrapper(func, unwind=True):
	def safe_chk(*argz, **kwz):
		if kwz.pop('unwind', unwind):
			return func(*argz, **kwz)
		try: return func(*argz, **kwz)
		except Exception as err:
			from traceback import extract_tb
			err = '\n'.join(it.chain(
				['-- {}: {}'.format(type(err).__name__, err)],
				err_traceback(sys.exc_info()[2]) ))
			signal_error(err)
			return True
	return safe_chk


@chk_wrapper
def chk_copyright( line,
		rx = re.compile( r'^# Copyright'
			r' (?P<dates>(?P<date>\d+)(-(?P<date_ext>\d+))?)'
			r' (?P<author>.+)$' ) ):
	match = rx.match(line)
	if not match: return False

	date_chk = datetime.now().year
	date_min, date_max = op.itemgetter('date', 'date_ext')(match.groupdict())
	if date_min == date_max:
		raise ChkException('Identical dates: {}'.format(match.group('dates')))
	date_min = int(date_min)
	date_max = int(date_max) if date_max is not None else date_min
	if date_min < date_chk and date_max < date_chk:
		raise ChkException('Obsolete dates: {}'.format(match.group('dates')))
	if date_min > date_max:
		raise ChkException( 'Dates ordering is wrong:'
			' {} ({} > {}!)'.format(match.group('dates'), date_min, date_max) )
	if date_min < 2005 or date_max > date_chk:
		raise ChkException( 'Dates are too far in'
			' the past/future: {}'.format(match.group('dates')) )

	author = match.group('author')
	if author.strip() != author:
		raise ChkException('Author name is padded with extra whitespaces')

	return author

@chk_wrapper
def chk_license( line,
		rx = re.compile( r'^# Distributed under the'
			' terms of the GNU General Public License v2' ) ):
	return bool(rx.match(line))

@chk_wrapper
def chk_definition(src, var):
	from ast import literal_eval
	src = iter(src)
	for line in src:
		if line.startswith(var): break
	else: raise ChkException('{} line not found'.format(var))
	while True:
		try: vardef = literal_eval(line.split('{}='.format(var), 1)[-1])
		except SyntaxError:
			try: line += next(src)
			except StopIteration:
				raise ChkException('{} line is not quoted properly'.format(var))
		else: break
	return vardef

@chk_wrapper
def chk_definition_len(src, var, min_len=10, max_len=None):
	vardef = chk_definition(src, var)
	if (min_len is not None and len(vardef) < min_len)\
			or (max_len is not None and len(vardef) > max_len):
		raise ChkException( 'Invalid definition length'
			' for {} ({}-{}):\n  {!r}'.format(var, min_len, max_len, vardef) )
	return vardef

@chk_wrapper
def chk_emptyline(src, count=1):
	for line in src:
		if not line:
			count -= 1
			if count <= 0: break
	else: raise ChkException('Missing empty line')

@chk_wrapper
def chk_ordering( vardef,
		token_grouper = lambda tokens: [list(tokens)],
		rx = re.compile(r'(~?\S+(\s+\[\[.+?\]\])?)', re.DOTALL) ):
	token_groups = token_grouper(
		it.imap(op.itemgetter(0), rx.findall(vardef)) )
	for tokens in token_groups:
		if sorted(tokens) != tokens:
			raise ChkException( 'Tokens must be'
				' sorted:\n  {}\nshould be:\n  {}'.format(
					', '.join(it.imap(repr, tokens)),
					', '.join(it.imap(repr, sorted(tokens)))) )

def _deps_grouper(tokens):
	thead, tbuff, token_groups = None, list(), dict()
	for token in tokens:
		if token.endswith(':'):
			if thead:
				if not tbuff:
					raise ChkException('Empty token group: {}'.format(thead))
				token_groups[thead], tbuff = tbuff, list()
			thead = token.rstrip(':')
		else: tbuff.append(token)
	if tbuff: token_groups[thead] = tbuff
	return token_groups.viewvalues()


@ft.partial(chk_wrapper, unwind=False)
def check_file(src):
	src = it.imap(op.methodcaller('strip', '\n\r'), src)

	chk = False
	for line in src:
		author = chk_copyright(line)
		if not author:
			src = it.chain([line], src)
			break
		if author == 'Mike Kazantsev': chk = True
	if not chk:
		raise ChkException('Forgot to add myself to a copyright')

	line = next(src)
	if not chk_license(line):
		raise ChkException('Invalid/missing license line: {}'.format(line))
	del line

	chk_emptyline(src)

	chk_definition_len(src, 'SUMMARY')
	chk_definition_len(src, 'DESCRIPTION')
	chk_emptyline(src)

	chk_definition_len(src, 'HOMEPAGE')
	chk_definition_len(src, 'DOWNLOADS')

	chk_emptyline(src)

	chk_definition_len(src, 'LICENCES', min_len=1)
	chk_definition_len(src, 'SLOT', min_len=1)
	chk_ordering(chk_definition_len(src, 'PLATFORMS', min_len=4))
	chk_ordering(chk_definition(src, 'MYOPTIONS'))
	chk_emptyline(src)

	chk_ordering(
		chk_definition(src, 'DEPENDENCIES'),
		token_grouper = _deps_grouper )
	chk_emptyline(src)

	chk_definition_len(src, 'BUGS_TO')


def check_db(cdb):
	global err_count

	if sys.argv[1:]:
		raise ValueError('This command takes no arguments')

	from subprocess import Popen, PIPE
	proc = Popen(['git', 'ls-files'], stdout=PIPE)
	git_files = set(it.imap(op.methodcaller('strip'), proc.stdout))
	proc.wait()

	errors = 0
	for k,v in cdb.items():
		path = join(base_dir, k)
		if not v or not isfile(path) or k not in git_files:
			del cdb[k]
			continue

		print('Checking path: {}'.format(k))
		err_count = 0
		check_file(open(path))
		if err_count: errors += 1

	sys.exit(min(errors, 31))


if __name__ == '__main__':
	with checker_db() as cdb: check_db(cdb)
