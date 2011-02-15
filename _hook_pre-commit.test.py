#!/usr/bin/python -B
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function


import itertools as it, operator as op, functools as ft
import unittest

import os, sys
os.environ['GIT_DIR'] = '.git'
mod = __import__('_hook_pre-commit')


class TestChkCopyright(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		from datetime import datetime
		cls.year = datetime.now().year
		cls.func = ft.partial(mod.chk_copyright, unit_test=True)

	def test_valid(self):
		author_chk = lambda line: self.assertEqual('Some Автор', self.func(line))
		author_chk('# Copyright {} Some Автор'.format(self.year))
		author_chk('# Copyright 2005-{} Some Автор'.format(self.year))
		author_chk('# Copyright {}-{} Some Автор'.format(self.year-1, self.year))
		author_chk('# Copyright {}-{} Some Автор'.format(2005, self.year))
		self.assertTrue('# Copyright {} Автор'.format(self.year))

	def test_invalid(self):
		exc_chk = lambda line: self.assertRaises(
			mod.ChkException, ft.partial(self.func, line) )
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
		cls.func = ft.partial(mod.chk_license, unit_test=True)

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
		cls.func = ft.partial(mod.chk_definition, var='SUMMARY', unit_test=True)
		cls.func_len = ft.partial(mod.chk_definition_len, var='SUMMARY', unit_test=True)
		cls.sum_oneline = r'SUMMARY="Some soft \"test\" \'тест waka\'."'
		cls.sum_multiline = [r'SUMMARY="Some soft \"test\" \'тест waka\'.',
			'yada yada', r'\"test2\" blah \blah \blah"']
		cls.sum_braced = [
			r'SUMMARY=( "Some (soft \"test\" \'тест (waka)\'."'
			' "--with-)" "some content"', '"moar УНИКОД stuff" )' ]

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
		self.assertTrue(self.func(self.sum_braced))
		self.assertIsNot(self.func(['SUMMARY=""']), False)
		self.assertTrue(self.func_len([self.sum_oneline]))
		self.assertTrue(self.func_len(self.sum_multiline))
		self.assertTrue(self.func_len(self.sum_braced))
		self.assertTrue(self.func_len(['SUMMARY="test"'], min_len=4, max_len=4))

	def test_invalid(self):
		exc_chk = lambda src, func=self.func, **kwz:\
			self.assertRaises(mod.ChkException, ft.partial(func, src, **kwz))
		exc_chk(self.sum_multiline[:-1])
		exc_chk(self.sum_oneline[:-1])
		exc_chk([' ' + self.sum_oneline])
		exc_chk([self.sum_oneline + '"'])
		exc_chk(self.sum_braced[:-1] + [self.sum_braced[-1] + '('])
		exc_chk(self.sum_braced[:-1] + [self.sum_braced[-1] + ')'])
		exc_chk(['SUMMARY="test"'], func=self.func_len)
		exc_chk(['SUMMARY="t', 'e', 's', 't"'], func=self.func_len)
		exc_chk(['SUMMARY=( "t', 'e', 's', 't" )'], func=self.func_len)
		exc_chk(['SUMMARY=( "t', 'e'*1000, 's', 't" )'], func=self.func_len, max_len=999)


class TestChkEmptyLine(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.func = ft.partial(mod.chk_emptyline, unit_test=True)

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
			self.assertRaises(mod.ChkException, ft.partial(self.func, src, **kwz))
		exc_chk([])
		exc_chk(['test', 'a', ' b', 'moar'])
		exc_chk(['test', '', ' b', 'moar'], count=2)


unittest.main()
