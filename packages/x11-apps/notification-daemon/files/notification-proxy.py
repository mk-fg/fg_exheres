#!/usr/bin/env python
# -*- coding: utf-8 -*-

####

optz = dict( qlen = 10, tbf_size = 4,
	tbf_tick = 15, tbf_max_delay = 60,
	tbf_inc = 2, tbf_dec = 2 )
poll_interval = 60
nid_gc_max_interval = 600

dbus_src = 'org.freedesktop.Notifications'
dbus_dst = 'org.freedesktop.NotificationCore'
dbus_path = '/org/freedesktop/Notifications'

urgency_levels = ['low', 'normal', 'critical']

####


from optparse import OptionParser
parser = OptionParser(usage='%prog [options]',
	description='Start dbus notification proxy')

parser.add_option('-f', '--no-fs-check',
	action='store_false', dest='fs_check', default=True,
	help='Dont queue messages if active window is fullscreen')
parser.add_option('-u', '--no-urgency-check',
	action='store_false', dest='urgency_check', default=True,
	help='Queue messages even if urgency is critical')
parser.add_option('--no-status-notify',
	action='store_false', dest='status_notify', default=True,
	help='Do not send notification on changes in proxy settings.')
parser.add_option('--filter-file', action='store', type='str', default='~/.notification_filter',
	help='Read simple scheme rules for filtering notifications from file (default: %default).')

parser.add_option('-s', '--tbf-size',
	action='store', dest='tbf_size', type='int',
	metavar='NUM', default=optz['tbf_size'],
	help='Token-bucket message-flow filter (tbf)'
		' bucket size (default: %default)')
parser.add_option('-t', '--tbf-tick',
	action='store', dest='tbf_tick', type='int',
	metavar='NUM', default=optz['tbf_tick'],
	help='tbf update interval (new token), so token_inflow'
		' = token / tbf_tick (default: %defaults)')
parser.add_option('-m', '--tbf-max-delay',
	action='store', dest='tbf_max_delay', type='int',
	metavar='NUM', default=optz['tbf_max_delay'],
	help='Maxmum amount of seconds, between'
		' message queue flush (default: %defaults)')
parser.add_option('-i', '--tbf-inc',
	action='store', dest='tbf_inc', type='int',
	metavar='NUM', default=optz['tbf_inc'],
	help='tbf_tick multiplier on consequent tbf'
		' overflow (default: %default)')
parser.add_option('-d', '--tbf-dec',
	action='store', dest='tbf_dec', type='int',
	metavar='NUM', default=optz['tbf_dec'],
	help='tbf_tick divider on successful grab from non-empty bucket,'
		' wont lower multiplier below 1 (default: %default)')

parser.add_option('-q', '--queue-len',
	action='store', dest='qlen', type='int',
	metavar='NUM', default=optz['qlen'],
	help='How many messages should be'
		' queued on tbf overflow  (default: %default)')

# parser.add_option('-l', '--log',
# 	action='store', dest='log', type='str', metavar='PATH',
# 	help='Write log to a given path instead of stderr')

parser.add_option('--debug',
	action='store_true', dest='debug',
	help='Enable debugging output (to stderr)')

optz, argz = parser.parse_args()
if argz: parser.error('This command takes no arguments')


import logging
logging.basicConfig(level=(logging.DEBUG if optz.debug else logging.WARNING))
log = logging.getLogger()

import itertools as it, operator as op, functools as ft
from dbus.mainloop.glib import DBusGMainLoop
from fgc.wm import Window
from fgc.fc import FC_TokenBucket, RRQ
from threading import Lock
import dbus, dbus.service, gobject, signal, cgi
import os, sys

from collections import deque
from time import time

from fgc.scheme import load, init_env
from fgc.err import ext_traceback
import re

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()

optz.filter_file = os.path.expanduser(optz.filter_file)


class NotifyProxy(dbus.service.Object):
	_queue_lock = Lock()
	_last_note = None # used to show last delayed notification as-is, if it's the only one
	_id_stack, _id_stack_gc = deque(), 0 # used to keep id's of last displayed notes, so they can be closed
	_dbus_method = ft.partial(dbus.service.method, dbus_src)
	plugged, timeout_cleanup = False, True

	def __init__(self, *argz, **kwz):
		tick_strangle_max = op.truediv(optz.tbf_max_delay, optz.tbf_tick)
		super(NotifyProxy, self).__init__(*argz, **kwz)
		self._notify_limit = FC_TokenBucket(
			tick=optz.tbf_tick, burst=optz.tbf_size,
			tick_strangle=lambda x: min(x*optz.tbf_inc, tick_strangle_max),
			tick_free=lambda x: max(op.truediv(x, optz.tbf_dec), 1) )
		self._notify_buffer = RRQ(optz.qlen)


	@property
	def ncore(self):
		return dbus.Interface(
			bus.get_object(dbus_dst, dbus_path),
			dbus_interface=dbus_dst )

	def _fake_path(self, data):
		return map( lambda xml: xml\
			.replace(dbus_path, dbus_path)\
			.replace(dbus_dst, dbus_src), data )

	@_dbus_method(in_signature='', out_signature='ssss')
	def GetServerInformation(self): return self._fake_path(self.ncore.GetServerInformation())

	@_dbus_method(in_signature='', out_signature='as')
	def GetCapabilities(self): return self._fake_path(self.ncore.GetCapabilities())


	@_dbus_method(in_signature='u', out_signature='')
	def CloseNotification(self, nid):
		if not nid:
			log.debug('Closing all notifications from displayed stack')
			while self._id_stack: # flush the stack
				nid, nid_ts = self._id_stack.popleft()
				self.ncore.CloseNotification(nid)
			self._id_stack_gc = 0
		else: return self.ncore.CloseNotification(nid)


	@_dbus_method(in_signature='', out_signature='')
	def Flush(self):
		log.debug('Manual flush of the notification buffer')
		return self.flush_buffer()


	@_dbus_method(in_signature='a{sb}', out_signature='')
	def Set(self, params):
		# Urgent-passthrough controls
		if params.pop('urgent_toggle', None): params['urgent'] = not optz.urgency_check
		try: val = params.pop('urgent')
		except KeyError: pass
		else:
			optz.urgency_check = val
			if optz.status_notify:
				self.forward( summary='Urgent messages passthrough {0}'\
					.format('enabled' if optz.urgency_check else 'disabled') )
		# Plug controls
		if params.pop('plug_toggle', None): params['plug'] = not self.plugged
		try: val = params.pop('plug')
		except KeyError: pass
		else:
			if val:
				self.plugged = True
				log.debug('Notification queue plugged')
				if optz.status_notify:
					self.forward( summary='Notification proxy: queue is plugged',
						body='Only urgent messages will be passed through'
							if optz.urgency_check else 'All messages will be stalled' )
			else:
				self.plugged = False
				log.debug('Notification queue unplugged')
				if optz.status_notify:
					self.forward(summary='Notification proxy: queue is unplugged')
				if self._notify_buffer:
					log.debug('Flushing plugged queue')
					self._flush_buffer(scheduled=False)
		# Timeout override
		if params.pop('cleanup_toggle', None): params['cleanup'] = not self.timeout_cleanup
		try: val = params.pop('cleanup')
		except KeyError: pass
		else:
			self.timeout_cleanup = val
			log.debug('Cleanup timeout: {}'.format(self.timeout_cleanup))
			if optz.status_notify:
				self.forward( summary='Notification proxy: cleanup timeout is {}'\
					.format('enabled' if self.timeout_cleanup else 'disabled') )
		# Notify about malformed arguments, if any
		if params and optz.status_notify:
			self.forward(summary='Notification proxy: unrecognized parameters', body=repr(params))


	def _update_stack(self, nid, timeout):
		ts = time()
		timeout = op.truediv(timeout, 1000) # ms -> s

		nid_ts = ts + ( nid_gc_max_interval
			if timeout <= 0 else min(nid_gc_max_interval, timeout) )
		self._id_stack.append((nid, nid_ts))

		if self._id_stack_gc < ts:
			log.debug( 'Cleaning up displayed'
				' notification ids stack (size: {0})'.format(len(self._id_stack)) )
			while self._id_stack: # gc cycle
				nid, nid_ts = self._id_stack.popleft()
				if nid_ts > ts:
					self._id_stack.appendleft((nid, nid_ts))
					self._id_stack_gc = nid_ts # time of next cycle
					break
			log.debug('Stack size after cleanup: {0}'.format(len(self._id_stack)))


	_filter_ts_chk = 0
	_filter_callback = None, 0

	def _notification_check(self, summary, body):
		(cb, mtime), ts = self._filter_callback, time()
		if self._filter_ts_chk < ts - poll_interval:
			self._filter_ts_chk = ts
			try: ts = int(os.stat(optz.filter_file).st_mtime)
			except (OSError, IOError): return True
			if ts > mtime:
				mtime = ts
				init_env({'~': lambda regex, string: bool(re.search(regex, string))})
				try: cb = load(optz.filter_file)
				except:
					ex, self._filter_callback = ext_traceback(), (None, 0)
					log.debug('Failed to load notification filters (from {}):\n{}'.format(optz.filter_file, ex))
					if optz.status_notify:
						self.forward(summary='Notification proxy: failed to load notification filters', body=ex)
					return True
				else:
					log.debug('(Re)Loaded notification filters')
					self._filter_callback = cb, mtime
		if cb is None: return True # no filtering defined
		elif not callable(cb): return bool(cb)
		try: return cb(summary, body)
		except:
			ex = ext_traceback()
			log.debug('Failed to execute notification filters:\n{}'.format(ex))
			if optz.status_notify:
				self.forward(summary='Notification proxy: notification filters failed', body=ex)
			return True



	def _escape_tags(self, text, encoding='utf-8'):
		if not isinstance(text, unicode): text = text.decode(encoding, 'replace')
		return cgi.escape(text).encode('ascii', 'xmlcharrefreplace')

	def forward( self, app_name='notification proxy', id=dbus.UInt32(),
			icon='', summary='', body='', actions=dbus.Array(signature='s'),
			hints=dict(urgency=dbus.Byte(urgency_levels.index('critical'), variant_level=1)), timeout=-1 ):
		summary, body = self._escape_tags(summary), self._escape_tags(body)
		nid = self.ncore.Notify( app_name, id, icon, summary,
			body, actions, hints, timeout if self.timeout_cleanup else 0 )
		self._update_stack(nid, timeout)
		return nid


	@dbus.service.method( dbus_src,
		in_signature='susssasa{sv}i', out_signature='u' )
	def Notify(self, app_name, id, icon, summary, body, actions, hints, timeout):
		try: urgency = int(hints[u'urgency'])
		except (KeyError, ValueError): urgency = None

		with self._queue_lock:
			self._last_note = app_name, id, icon, \
				summary, body, actions, hints, timeout

			plug = self.plugged or (optz.fs_check and Window.get_active().fullscreen)
			urgent = optz.urgency_check and urgency == urgency_levels.index('critical')

			if urgent:
				log.debug( 'Urgent message immediate passthru'
					', tokens left: {0}'.format(self._notify_limit.tokens) )
				self._notify_limit.consume(block=False)
				return self.forward(app_name, id, icon, summary, body, actions, hints, timeout)

			if not self._notification_check(summary, body):
				log.debug('Dropped notification due to negative filtering result')
				return 0

			if plug or not self._notify_limit.consume(block=False):
				# Delay notification
				to = self._notify_limit.get_eta() if not plug else poll_interval
				if to > 1: # no need to bother otherwise, note that it'll be an extra token ;)
					self._notify_buffer.append((summary, body))
					to = int(to) + 1 # +1 is to ensure token arrival by that time
					log.debug( 'Queueing notification. Reason: {0}. Flush attempt in {1}s'\
						.format('plug or fullscreen window detected' if plug else 'notification rate limit', to) )
					signal.alarm(to)
					return 0
			signal.alarm(0) # no async calls past this point: either way it's a flush

		if self._notify_buffer:
			self._notify_buffer.append((summary, body))
			log.debug('Token-flush of notification queue')
			return self.flush_buffer(scheduled=False)
		else:
			log.debug('Token-pass, {0} token(s) left'.format(self._notify_limit.tokens))
			return self.forward(app_name, id, icon, summary, body, actions, hints, timeout)


	def _flush_buffer(self, signum=signal.SIGALRM, frame=None, scheduled=True):
		signal.alarm(0) # reset alarm, if present
		if not self._queue_lock.acquire(False): return # queue-op in progress already
		self._queue_lock.release()

		log.debug( 'Flushing notification queue ({0} msgs, {1} dropped)'\
			.format(len(self._notify_buffer), self._notify_buffer.dropped) )

		if scheduled: self._notify_limit.consume()
		if signum != signal.SIGALRM:
			self._notify_buffer.append(( 'System',
				'Received death-signal ({0}), shutting down...'.format(signum) ))
		elif optz.fs_check and scheduled and (Window.get_active().fullscreen or self.plugged):
			log.debug( '{0} detected, delaying buffer flush by {1}s'\
				.format(('Fullscreen window' if not self.plugged else 'Plug'), poll_interval) )
			signal.alarm(poll_interval)
			return 0

		if self._notify_buffer:
			status = self.forward(*self._last_note) \
				if len(self._notify_buffer) == 1 else self.forward(
					'notification-feed', dbus.UInt32(0), 'FBReader',
					'Feed' if not self._notify_buffer.dropped
						else 'Feed ({0} dropped)'.format(self._notify_buffer.dropped),
					'\n\n'.join(it.starmap('--- {0}\n  {1}'.format, self._notify_buffer)),
					dbus.Array(signature="s"), dbus.Dictionary(signature='sv'), -1 )
			self._notify_buffer.flush()
			log.debug('Notification buffer flushed')
		else:
			log.debug('Notification buffer is empty - nothing to flush')
			status = None

		if signum != signal.SIGALRM:
			log.debug('Got termination signal ({0}), shutting down'.format(signum))
			loop.quit()

		return status


	@ft.wraps(_flush_buffer)
	def flush_buffer(self, *argz, **kwz):
		# Needed to get exceptions outta gobject loop
		try: return self._flush_buffer(*argz, **kwz)
		except Exception as err:
			log.error(ext_traceback())
			raise



interceptor = NotifyProxy(bus, dbus_path, dbus.service.BusName(dbus_src, bus))
signal.signal(signal.SIGALRM, interceptor.flush_buffer)

loop = gobject.MainLoop()
log.debug('Starting gobject loop')
loop.run()
