#!/sbin/runscript
# Copyright 1999-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

depend() {
	before apache2 lighttpd nginx
}

start() {
	ebegin "Starting sslh"
	start-stop-daemon --start \
		--pidfile /var/run/sslh.pid \
		--exec /usr/sbin/sslh -- \
			-u ${USER} -p ${LISTEN} -s ${SSH} -l ${SSL} \
			-P /var/run/sslh.pid
	eend $?
}

stop() {
	ebegin "Stopping sslh"
	start-stop-daemon --stop --pidfile /var/run/sslh.pid
	eend $?
}

