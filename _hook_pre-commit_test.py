#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function


import itertools as it, operator as op, functools as ft
import unittest

from datetime import datetime
import os, sys, io, re

os.environ['GIT_DIR'] = '.git'
mod = __import__('_hook_pre-commit')


class TestChkCopyright(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.year = datetime.now().year
		cls.func = ft.partial(mod.chk_copyright, unwind=True)

	def test_valid(self):
		author_chk = lambda line: self.assertEqual('Some Автор', self.func(line))
		author_chk('# Copyright {} Some Автор'.format(self.year))
		author_chk('# Copyright 2005-{} Some Автор'.format(self.year))
		author_chk('# Copyright {}-{} Some Автор'.format(self.year-1, self.year))
		author_chk('# Copyright {}-{} Some Автор'.format(2005, self.year))
		self.assertTrue('# Copyright {} Автор'.format(self.year))

	def test_invalid(self):
		exc_chk = lambda line: self.assertRaises(
			mod.ChkHeadersError, ft.partial(self.func, line) )
		exc_chk('# Copyright {0}-{0} Some Автор'.format(self.year))
		exc_chk('# Copyright 2004 Some Автор')
		exc_chk('# Copyright {} Some Автор'.format(self.year+1))
		exc_chk('# Copyright {}-{} Some Автор'.format(self.year-2, self.year-1))
		exc_chk('# Copyright {}-{} Some Автор'.format(self.year, self.year-1))
		exc_chk('# Copyright 2004-{} Some Автор'.format(self.year))
		exc_chk('# Copyright {}{} Some Автор'.format(self.year-1, self.year))
		exc_chk('# Copyright {}  Some Автор'.format(self.year))
		exc_chk('# Copyright {} Some Автор '.format(self.year))

	def test_false_match(self):
		false_chk = lambda line: self.assertFalse(self.func(line))
		false_chk(' # Copyright {} Some Автор'.format(self.year))
		false_chk('# Copyright 20x Some Автор')
		false_chk('# Copyright XIX Some Автор')
		false_chk('# Copyright {} '.format(self.year))
		false_chk('# Copyright  {} Some Автор'.format(self.year))
		false_chk('#  Copyright {} Some Автор'.format(self.year))
		false_chk('#\tCopyright {} Some Автор'.format(self.year))
		false_chk('# (C) {} Some Автор'.format(self.year))
		false_chk('# Copyright {}--{} Some Автор'.format(self.year-1, self.year))
		false_chk('# Copyright - Some Автор'.format(self.year-1, self.year))
		false_chk('# Copyright {}- Some Автор'.format(self.year-1, self.year))
		false_chk('# Copyright {}-{}- Some Автор'.format(self.year-1, self.year))


class TestChkLicense(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_license, unwind=True)

	def test_valid(self):
		self.assertTrue(self.func('# Distributed under the terms of the GNU General Public License v2'))

	def test_invalid(self):
		false_chk = lambda line: self.assertFalse(self.func(line))
		false_chk(' # Distributed under the terms of the GNU General Public License v2')
		false_chk('# Distributed under the  terms of the GNU General Public License v2')
		false_chk('# Distributed')
		false_chk('GNU General Public License v2')


class TestChkDef(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_definition, var='SUMMARY', unwind=True)
		cls.func_len = ft.partial(mod.chk_definition_len, var='SUMMARY', unwind=True)
		cls.sum_oneline = r'SUMMARY="Some soft \"test\" \'тест waka\'."'
		cls.sum_multiline = [r'SUMMARY="Some soft \"test\" \'тест waka\'.',
			'yada yada', r'\"test2\" blah \blah \blah"']

	def test_cont(self):
		src_lst = ['test', '', '', self.sum_oneline, '', 'waka waka']
		src = iter(src_lst)
		self.assertTrue(self.func(src))
		self.assertEqual(list(src), src_lst[-2:])
		src_lst = ['test', '', ''] + self.sum_multiline + ['', 'waka waka']
		src = iter(src_lst)
		self.assertTrue(self.func(src))
		self.assertEqual(list(src), src_lst[-2:])

	def test_valid(self):
		self.assertTrue(self.func([self.sum_oneline]))
		self.assertTrue(self.func([self.sum_oneline + '   ']))
		self.assertTrue(self.func([self.sum_oneline + '"ext"']))
		self.assertTrue(self.func(self.sum_multiline))
		self.assertTrue(self.func(['Some line'] + self.sum_multiline + ['Other line']))
		self.assertIsNot(self.func(['SUMMARY=""']), False)
		self.assertTrue(self.func_len([self.sum_oneline]))
		self.assertTrue(self.func_len(self.sum_multiline))
		self.assertTrue(self.func_len(['SUMMARY="test"'], min_len=4, max_len=4))

	def test_invalid(self):
		exc_chk = lambda src, **kwz:\
			self.assertRaises(mod.ChkDefError, ft.partial(self.func, src, **kwz))
		exc_chk(self.sum_multiline[:-1])
		exc_chk(self.sum_oneline[:-1])
		exc_chk([' ' + self.sum_oneline])
		exc_chk([self.sum_oneline + '"'])
		exc_chk = lambda src, **kwz:\
			self.assertRaises(mod.ChkDefLenError, ft.partial(self.func_len, src, **kwz))
		exc_chk(['SUMMARY="test"'])
		exc_chk(['SUMMARY="t', 'e', 's', 't"'])
		exc_chk(['SUMMARY="t', 'e', 's', 't"'])
		exc_chk(['SUMMARY="test"'], min_len=5)
		exc_chk(['SUMMARY="t', 'e'*1000, 's', 't"'], max_len=999)


class TestChkEmptyLine(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_emptyline, unwind=True)

	def test_cont(self):
		src_lst = ['test', '', '', 'moar']
		src = iter(src_lst)
		self.assertIsNone(self.func(src))
		self.assertEqual(list(src), src_lst[-2:])
		src = iter(src_lst)
		self.assertIsNone(self.func(src, count=2))
		self.assertEqual(list(src), src_lst[-1:])

	def test_valid(self):
		self.assertIsNone(self.func(['test', '', '', 'moar']))
		self.assertIsNone(self.func(['test', '', '', 'moar'], count=2))

	def test_invalid(self):
		exc_chk = lambda src, **kwz:\
			self.assertRaises(mod.ChkEmptylineError, ft.partial(self.func, src, **kwz))
		exc_chk([])
		exc_chk(['test', 'a', ' b', 'moar'])
		exc_chk(['test', '', ' b', 'moar'], count=2)


class TestChkOrdering(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_ordering, unwind=True)

	def test_valid(self):
		self.assertIsNone(self.func('~amd64 ~x86'))
		self.assertIsNone(self.func('amd64 x86 ~amd64 ~x86'))
		self.assertIsNone(self.func('flag1 flag2 flag_x some-option'))
		self.assertIsNone(self.func('flag-a [[ description = [ some stuff ]\n'
			' other-stuff = [ something else ] ]]\n flag-b [[ some stuff ]] flag-c'))

	def test_invalid(self):
		exc_chk = lambda src:\
			self.assertRaises(mod.ChkOrderingError, ft.partial(self.func, src))
		exc_chk('~x86 ~amd64')
		exc_chk('amd64 ~amd64 x86 ~x86')
		exc_chk('flag_x flag1')
		exc_chk('flag-b [[ description = [ some stuff ]\n'
			' other-stuff = [ something else ] ]]\n flag-a [[ some stuff ]]')
		exc_chk('flag-b [[ description = [ some stuff ]\n'
			' other-stuff = [ something else ] ]]\n flag-a')

	def test_groups_valid(self):
		self.assertIsNone(self.func('''aio chunk debug pam
			nginx_modules_http:
				access addition auth_basic autoindex [[ test = [ waka ] ]]
			nginx_modules_mail: imap pop3 smtp'''))
		self.assertIsNone(self.func('''nginx_modules_http: access $MORE_TOKENS'''))
		self.assertIsNone(self.func('''nginx_modules_http: $WHATEVER'''))
		self.assertIsNone(self.func('''$MORE_TOKENS access'''))
		self.assertIsNone(self.func('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				sys-libs/zlib openssl? ( aaa/stuff )
			test:
				dev-lang/tcl'''))
		self.assertIsNone(self.func('''
			token2 waka some-stuff? ( yada )
			build+run:
				dev-db/sqlite[>=3.7.0] sys-libs/zlib
				openssl? (
					aaa/stuff other/stuff
					waka/waka ) [[ some-crap = [ other-crap ] ]]
			test:
				dev-lang/tcl'''))

	def test_groups_invalid(self):
		exc_chk = lambda src: self.assertRaises(
			mod.ChkOrderingError, ft.partial(self.func, src) )
		exc_chk('''aio debug chunk pam
			nginx_modules_http: access addition auth_basic autoindex
			nginx_modules_mail: imap pop3 smtp''')
		exc_chk('''aio debug
			pam nginx_modules_http: access addition auth_basic
			nginx_modules_mail: imap pop3 smtp''')
		exc_chk('''aio debug
			nginx_modules_http:
			nginx_modules_mail: imap pop3 smtp''')
		exc_chk('''nginx_modules_http: test nginx_modules_mail: imap''')
		exc_chk('''waka? ( stuff ) nginx_modules_http: test''')
		exc_chk('''build+run:
				dev-libs/openssl
				dev-db/sqlite[>=3.7.0]
				sys-libs/zlib
			test:
				dev-lang/tcl''')
		exc_chk('''build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				openssh? ( aaa/stuff )
				sys-libs/zlib
			test:
				dev-lang/tcl''')
		exc_chk('''run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				openssh? ( aaa/stuff )
				sys-libs/zlib
			build:
				dev-lang/tcl''')


class TestChkDeps(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_deps, unwind=True)

	def test_grouper_valid(self):
		func = ft.partial(mod.chk_ordering, token_grouper=mod._deps_grouper, unwind=True)
		self.assertIsNone(self.func('''\nbuild+run:\n $WHATEVER\n'''))
		self.assertIsNone(self.func('''\nbuild+run:\n lib $MORE_TOKENS\n'''))
		self.assertIsNone(self.func('''\nrun:\n $MORE_TOKENS lib\n'''))
		self.assertIsNone(func('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				sys-libs/zlib
			test:
				dev-lang/tcl
			'''))
		self.assertIsNone(func('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				sys-libs/zlib openssl? ( aaa/stuff )
			test:
				dev-lang/tcl'''))
		self.assertIsNone(func('''
			build+run:
				dev-db/sqlite[>=3.7.0] sys-libs/zlib
				openssl? (
					aaa/stuff other/stuff
					waka/waka ) [[ some-crap = [ other-crap ] ]]
			test:
				dev-lang/tcl'''))

	def test_grouper_invalid(self):
		exc_chk = lambda src: self.assertRaises( mod.ChkOrderingError,
			ft.partial(mod.chk_ordering, src, token_grouper=mod._deps_grouper, unwind=True) )
		exc_chk('''build+run:
				dev-libs/openssl
				dev-db/sqlite[>=3.7.0]
				sys-libs/zlib
			test:
				dev-lang/tcl''')
		exc_chk('''build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				openssh? ( aaa/stuff )
				sys-libs/zlib
			test:
				dev-lang/tcl''')
		exc_chk('''run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				openssh? ( aaa/stuff )
				sys-libs/zlib
			build:
				dev-lang/tcl''')

	def test_valid(self):
		self.assertIsNone(self.func('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				sys-libs/zlib
			test:
				dev-lang/tcl\n'''))

	def test_invalid(self):
		exc_chk = lambda src:\
			self.assertRaises(mod.ChkDepsError, ft.partial(self.func, src))
		exc_chk('run: dev-db/sqlite[>=3.7.0] dev-libs/openssl sys-libs/zlib')
		exc_chk('''build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				sys-libs/zlib
			test:
				dev-lang/tcl\n''')
		exc_chk('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				sys-libs/zlib
			test: dev-lang/tcl\n''')
		exc_chk('''
			build+run:
				dev-db/sqlite[>=3.7.0]
				dev-libs/openssl
				sys-libs/zlib
			test:
				dev-lang/tcl''')





class TestChkFull(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.check_file, unwind=True)
		cls.sample = '''# Copyright %s Mike Kazantsev
# Distributed under the terms of the GNU General Public License v2
# Based upon 'nbd-2.9.15.ebuild' from Gentoo, which is:
#  Copyright 1999-2010 Gentoo Foundation

SOME_VAR="waka waka"

require sourceforge flag-o-matic

# Comment

SUMMARY="Userland client/server for kernel network block device"
DESCRIPTION=""

LICENCES="GPL-2"
SLOT="0"
PLATFORMS="~amd64 ~x86"
MYOPTIONS=""

# Moar comments
DEPENDENCIES="
	build:
		dev-util/pkg-config
	build+run:
		dev-libs/glib[>=2.0]
"

BUGS_TO="mk.fraggod@gmail.com"


DEFAULT_SRC_PREPARE_PATCHES=( -p0 "${FILES}/headers.patch" )
DEFAULT_CONFIGURE_ENABLES=( lfs syslog )

src_prepare() {
	default
	edo sed -i 's:/usr/bin/klcc:/suck/it/k/l/c/c:g' configure
	edo mkdir -p "${WORK}/inc-after/linux"
	edo cp "${FILES}/linux-include.h" "${WORK}/inc-after/linux/nbd.h"
	append-flags -idirafter "${WORK}/inc-after"
}

src_compile() {
	default
	emake -C gznbd
}

src_install() {
	default
	dobin gznbd/gznbd
}

src_test_net_switch() {
	esandbox $1 inet6:::/128@$2
	esandbox $1 --connect inet6:::/128@$2
	esandbox $1 --connect  inet:0.0.0.0/32@$2
	esandbox $1 --connect inet:127.0.0.1/32@$2
}

src_test() {
	src_test_net_switch allow_net 11111-11114
	default
	src_test_net_switch disallow_net 11111-11114
}
'''.replace('{', '{{').replace('}', '}}').replace('%s', '{}').format(datetime.now().year)

	def test_valid(self):
		replace_ = lambda rx, repl, *more, **kwz: re.sub(
			rx, repl, replace_(*more, flags=kwz.pop('flags', 0))
				if more else self.sample, flags=kwz.pop('flags', 0) )
		replace = lambda *more: io.StringIO(replace_(*more))
		self.assertIsNone(self.func(io.StringIO(self.sample)))
		self.assertIsNone(self.func(replace('(BUGS_TO.+?\n).*', r'\1')))

	def test_invalid(self):
		exc_chk = lambda src, exc=mod.ChkError:\
			self.assertRaises(exc, ft.partial(self.func, src))
		not_ = lambda chk: (lambda line: not chk(line))
		replace_ = lambda rx, repl, *more, **kwz: re.sub(
			rx, repl, replace_(*more, flags=kwz.pop('flags', 0))
				if more else self.sample, flags=kwz.pop('flags', 0) )
		replace = lambda *more: io.StringIO(replace_(*more))
		drop = lambda rx, src=None: it.ifilter(
			not_(re.compile(rx).search),
			src or io.StringIO(self.sample) )
		for missing_line in ('Copyright', 'License', 'require',
			'SUMMARY', 'DESCRIPTION', 'LICENCES', 'SLOT', 'PLATFORMS', 'MYOPTIONS',
			'DEPENDENCIES', 'BUGS_TO'): exc_chk(drop(missing_line))
		exc_chk(replace('DESCRIPTION', r'require stuff\n\0'))
		exc_chk(replace('require .*', '', 'DEPENDENCIES', r'require stuff\0'))
		exc_chk(replace('(SLOT.*\n)(PLATFORMS.*\n)', r'\2\1'))
		exc_chk(replace(r'gmail\.com', r'example.com'))
		for spaced_line in 'LICENCES', '# Moar', 'BUGS_TO':
			exc_chk(replace('\n({})'.format(spaced_line), r'\1'))
		for spaced_line in 'SLOT', 'PLATFORMS', 'DESCRIPTION':
			exc_chk(replace('({})'.format(spaced_line), r'\n\1'))
		exc_chk(io.StringIO(self.sample.strip()))
		exc_chk(io.StringIO(self.sample + '\n'))


if __name__ == '__main__': unittest.main()
