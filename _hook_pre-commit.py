#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function


import itertools as it, operator as op, functools as ft
from datetime import datetime
import os, sys, re
from os.path import join, isfile, dirname, basename
from io import open

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

class ChkError(Exception):
	def __init__(self, message, line=None):
		self.line = line
		super(ChkError, self).__init__(message)

class ChkHeadersError(ChkError): pass
class ChkDefError(ChkError): pass
class ChkDefLenError(ChkError): pass
class ChkOrderingError(ChkError): pass
class ChkDepsError(ChkError): pass
class ChkEmptylineError(ChkError): pass
class ChkFullError(ChkError): pass
class ChkMetaError(ChkError): pass


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
		err.append('  {}[{}]: {!r}{}'.format(
			frame.f_code.co_name, frame.f_lineno, line.strip(),
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
def chk_copyright( line, prior=False,
		rx = re.compile( r'^# Copyright( \(c\))?'
			r' (?P<dates>(?P<date>\d+)(-(?P<date_ext>\d+))?(,\s*\d+)*)'
			r' (?P<author>.+)$' ) ):
	match = rx.match(line)
	if not match: return False
	if prior: return match.group('author')

	date_chk = datetime.now().year
	date_min, date_max = op.itemgetter('date', 'date_ext')(match.groupdict())
	if date_min == date_max:
		raise ChkHeadersError('Identical dates: {}'.format(match.group('dates')))
	date_min = int(date_min)
	date_max = int(date_max) if date_max is not None else date_min
	# if date_min < date_chk and date_max < date_chk:
	# 	raise ChkHeadersError('Obsolete dates: {}'.format(match.group('dates')))
	if date_min > date_max:
		raise ChkHeadersError( 'Dates ordering is wrong:'
			' {} ({} > {}!)'.format(match.group('dates'), date_min, date_max) )
	if date_min < 2005 or date_max > date_chk:
		raise ChkHeadersError( 'Dates are too far in'
			' the past/future: {}'.format(match.group('dates')) )

	author = match.group('author')
	if author.strip() != author:
		raise ChkHeadersError('Author name is padded with extra whitespaces')

	return author

@chk_wrapper
def chk_license( line,
		rx = re.compile( r'^# Distributed under the'
			' terms of the GNU General Public License v2' ) ):
	return bool(rx.match(line))

@chk_wrapper
def chk_definition(src, var, nextline=False):
	from ast import literal_eval
	src = iter(src)
	for line in src:
		if line.startswith(var): break
		if nextline: raise ChkDefError('Next line with {} not found'.format(var))
	else: raise ChkDefError('{} line not found'.format(var))
	while True:
		try:
			vardef = literal_eval('""{}""'.format(
				line.split('=', 1)[-1].strip() ))
		except SyntaxError:
			try: line += next(src)
			except StopIteration:
				raise ChkDefError('{} line is not quoted properly'.format(var))
		else: break
	return vardef

@chk_wrapper
def chk_definition_len(src, var, nextline=False, min_len=10, max_len=None):
	vardef = chk_definition(src, var, nextline=nextline)
	if (min_len is not None and len(vardef) < min_len)\
			or (max_len is not None and len(vardef) > max_len):
		raise ChkDefLenError( 'Invalid definition length'
			' for {} ({}-{}):\n  {!r}'.format(var, min_len, max_len, vardef) )
	return vardef

@chk_wrapper
def chk_emptyline(src, count=1):
	for line in src:
		if not line.strip('\n'):
			count -= 1
			if count <= 0: break
	else: raise ChkEmptylineError('Missing empty line')

def _standard_grouper(tokens):
	thead, tbuff, token_groups = None, list(), list()
	token_last = shext = None
	for token_nl in tokens:
		token = token_nl.strip()
		if token.startswith('$'):
			shext = True
			continue
		if token.endswith(':'):
			if token_last and not token_last[-1] in '\n':
				raise ChkOrderingError('Inline token group: {}'.format(token[:-1]))
			if thead and not tbuff and not shext:
				raise ChkOrderingError('Empty token group: {}'.format(thead))
			token_groups.append((thead, tbuff))
			tbuff, shext = list(), False
			thead = token.rstrip(':')
		else: tbuff.append(token)
		token_last = token_nl
	if tbuff: token_groups.append((thead, tbuff))
	return token_groups

@chk_wrapper
def chk_ordering( vardef,
		token_grouper = _standard_grouper,
		sort_key = lambda token: token if token\
			.split(None, 1)[0].endswith('?') else '\x00{}'.format(token),
		rx = re.compile(r'(' r'(~?\S+)' r'(\s+\([^)]+\))?' r'(\s+\[\[.+?\]\])?' r'(\n)?' r')', re.DOTALL),
		**grouper_kwz ):
	tokens = rx.findall(vardef)
	if len(tokens) > 10:
		print('Too long list of tokens, ignoring')
		return
	token_groups = token_grouper(it.ifilter( lambda t: t != '||',
		it.imap(lambda m: m[1] + m[4], tokens) ), **grouper_kwz)
	tokens = map( lambda t: '\0' if t is None else t,
		it.imap(op.itemgetter(0), token_groups) )
	if tokens != sorted(tokens):
		raise ChkOrderingError( 'Token groups must be'
			' sorted:\n  {}\nshould be:\n  {}'.format(
					' '.join(tokens), ' '.join(sorted(tokens, key=sort_key)) ) )
	for tokens in it.imap(op.itemgetter(1), token_groups):
		if ')' in tokens or '(' in tokens:
			print('SKIPPED: Failed to parse tokens: {}'.format(', '.join(tokens)))
			continue
		if sorted(tokens, key=sort_key) != tokens:
			raise ChkOrderingError( 'Tokens must be'
				' sorted:\n  {}\nshould be:\n  {}'.format(
					' '.join(tokens), ' '.join(sorted(tokens, key=sort_key)) ) )

@chk_wrapper
def chk_deps(deps):
	if not deps.endswith('\n') or not deps.startswith('\n'):
		raise ChkDepsError('Dependencties are written inline or quoted lisp-style')
	if 'providers:' in deps:
		print('SKIPPED: deps are too complex for simple checks')
		return
	chk_ordering(deps, token_grouper = _deps_grouper)

def _deps_grouper(tokens):
	thead, tbuff, token_groups = None, list(), list()
	token_last = shext = None
	for token_nl in tokens:
		token = token_nl.strip()
		if token.startswith('$'):
			shext = True
			continue
		if token.endswith(':'):
			if token_last and not token_last[-1] in '\n?':
				raise ChkOrderingError('Inline token group: {}'.format(token[:-1]))
			if not token_nl.endswith('\n'):
				raise ChkDepsError('Deps\' categories and their contents are written inline')
			if thead:
				if not tbuff:
					raise ChkDepsError('Empty token group: {}'.format(thead))
				token_groups.append((thead, tbuff))
				tbuff, shext = list(), False
			thead = token.rstrip(':')
		else: tbuff.append(token)
		token_last = token_nl
	if tbuff:
		if thead is None:
			raise ChkDepsError('Dependencies are not categorized')
		token_groups.append((thead, tbuff))
	return token_groups


@ft.partial(chk_wrapper, unwind=False)
def check_file(src, exheres=None, category=None):
	author = chk_copyright(next(src))
	if author != 'Mike Kazantsev':
		raise ChkFullError('Forgot to add myself to a copyright')
	for line in src:
		if not chk_copyright(line, prior=True): break

	if not chk_license(line):
		raise ChkFullError('Invalid/missing license line: {}'.format(line))
	del line

	chk_emptyline(src)

	# some exlibs can define HOMEPAGE and DOWNLOADS
	exlib_src = '-scm.' in exheres or category == 'virtual'
	exlib_meta = exlib_deps = False
	for line in src:
		if line.startswith('require'):
			for mod in line.split():
				if mod in ( 'perl-module', 'sourceforge', 'googlecode', 'gnu',\
						'gnome-2', 'gnome.org', 'launchpad', 'hackage', 'pypi', 'gem',
						'enlightenment' )\
					or mod.startswith('scm-'): exlib_src = True
				if mod in ('ejabberd-module', 'perl-module'): exlib_meta = True
				if mod in ('hackage', 'perl-module'): exlib_deps = True
				# No further checks if exheres is just an extension of ad-hoc exlib
				if exheres and exheres.startswith(mod)\
						or mod == 'mozilla-app': # ...or some special cases
					chk_emptyline(src)
					chk_ordering(chk_definition_len(src, 'PLATFORMS', min_len=4))
					return
			chk_emptyline(src)
			break
		if line.startswith('SUMMARY'):
			src = it.chain([line], src)
			break
	src, src_chk = it.tee(src, 2)
	for line in src_chk:
		if line.strip().startswith('require '):
			raise ChkFullError('More than one or misplaced require line')
	del line

	chk_definition_len(src, 'SUMMARY')
	line = next(src)
	if line.strip():
		chk_definition_len( it.chain([line], src),
			'DESCRIPTION', nextline=True, min_len=50, max_len=200 )
		chk_emptyline(src)
	del line

	if not exlib_src:
		chk_definition_len(src, 'HOMEPAGE', nextline=True)
		chk_definition(src, 'DOWNLOADS', nextline=True)
		chk_emptyline(src)

	if not exlib_meta:
		chk_definition_len(src, 'LICENCES', min_len=1)
		chk_definition_len(src, 'SLOT', nextline=True, min_len=1)
	chk_ordering(chk_definition_len(src, 'PLATFORMS', nextline=not exlib_meta, min_len=4))
	if not exlib_meta:
		optz = chk_definition(src, 'MYOPTIONS')
		if 'requires' not in optz: chk_ordering(optz)
		chk_emptyline(src)

	if not exlib_deps:
		deps = chk_definition(src, 'DEPENDENCIES')
		if deps and '$(' not in deps: chk_deps(deps)
		chk_emptyline(src)

	if os.environ['EMAIL'] not in chk_definition_len(src, 'BUGS_TO'):
		raise ChkFullError('No public email (gmail account) specified in BUGS_TO')

	src, src_chk = it.tee(src, 2)
	econf_included_tokens = dict(it.izip(
		it.imap('--{}dir'.format, 'man info data doc sysconf localstate'.split(' ')),
		'/usr/share/man /usr/share/info /usr/share  /etc /var/lib'.split(' ') ))
	errs = list()
	for line in src_chk:
		if re.search(r'./configure\b', line):
			if errs:
				print('Found manual ./configure call, skipping checks for "--*dir" options')
				errs = list()
			break
		for token,val in econf_included_tokens.viewitems():
			if token in line:
				line_val = line.split('=', 1)[-1].split(None, 1)[0].rstrip('\\\n')
				if line_val == val:
					errs.append(ChkFullError( 'Econf-provided'
						' directive definition specified: {}'.format(token) ))
				else:
					errs.append('Redefinition of econf-provided'
						' directive: {} ({} != {})'.format(token, val, line_val))
	for err in errs:
		if isinstance(err, unicode): print(err)
		else: raise err
	del src_chk, errs

	line, trailing_lines = None, list()
	for line in src:
		if not line.strip(): trailing_lines.append(line)
		else: trailing_lines = list()
	if line and not line.endswith('\n'): raise ChkFullError('No final newline')
	if trailing_lines: raise ChkFullError('{} trailing empty lines'.format(len(trailing_lines)))


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
		check_file( open(path, encoding='utf-8'),
			exheres=basename(path), category=basename(dirname(dirname(path))) )
		if err_count: errors += 1

	return errors


def check_categories(): # no tests
	cat_real = set(os.listdir(join(base_dir, 'packages')))
	cat_conf = list(it.imap( op.methodcaller('strip'),
		open(join(base_dir, 'metadata', 'categories.conf')) ))
	if sorted(cat_conf) != cat_conf: signal_error('Categories need to be sorted')
	cat_conf = set(cat_conf)
	if cat_conf != cat_real:
		cat_err = cat_real - cat_conf
		if cat_err: signal_error('Missing categories in metadata: {}'.format(', '.join(cat_err)))
		cat_err = cat_conf - cat_real
		if cat_err: signal_error('Non-existing categories in metadata: {}'.format(', '.join(cat_err)))


def _parse_licences(tokens): # no tests
	for token in tokens:
		if token.endswith('?'): continue
		if token in ['(', ')', '||']: continue
		if token == '[[':
			for token in tokens:
				if token == ']]': break
			continue
		yield token

def check_licences(): # no tests
	from glob import glob
	masters = it.chain.from_iterable(
		it.ifilter(None, line.split('=', 1)[-1].split())
		for line in open(join(base_dir, 'metadata', 'layout.conf'))
		if line.startswith('masters') )
	masters = it.chain([join(base_dir, 'licences')], it.chain.from_iterable(
		[ '/var/db/paludis/*/{}/licences'.format(repo),
			'/var/db/paludis/*/{}/licenses'.format(repo) ] for repo in masters ))
	available_licences = set(it.chain.from_iterable(
		it.imap(os.listdir, it.chain.from_iterable(it.imap(glob, masters))) ))

	from subprocess import Popen, PIPE
	proc = Popen(['grep', '-rA10', 'LICENCES=', join(base_dir, 'packages')], stdout=PIPE)
	src = proc.stdout
	from ast import literal_eval
	for line in src:
		if 'LICENCES' in line:
			exheres = line.split(':', 1)[0].split(base_dir)[-1].lstrip('/')
			line = line.split('=', 1)[-1]
			while True:
				try: vardef = literal_eval('""{}""'.format(line.strip()))
				except SyntaxError:
					try: line += next(src).split('-\t', 1)[-1]
					except StopIteration:
						signal_error('LICENCES line is not quoted properly')
						break
				else: break
			unknown_licences = set(_parse_licences(iter(vardef.split()))) - available_licences
			if unknown_licences:
				signal_error('Unknown licenses in {}: {}'.format(exheres, ', '.join(unknown_licences)))
	proc.wait()



if __name__ == '__main__':
	with checker_db() as cdb: check_db(cdb)
	check_categories()
	check_licences()
	sys.exit(min(err_count, 31))
