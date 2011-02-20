#!/usr/bin/perl

# Simple perl script to list files with a given CVS tag
# Copyright (C) 2002,2003,2004 Erik Cumps <erik.cumps@icos.be>
#
# This file may be distributed under the terms of the GNU Public License.
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# $Id: lstag,v 1.3 2004/11/17 12:23:19 ec Exp $

use strict;

$::VERSION = "1.3";
$::cvs_ID = '$Id: lstag,v 1.3 2004/11/17 12:23:19 ec Exp $'; #'

# Prints usage info
sub Usage
{
	print "Usage: $0 [-d cvsroot] command [module]\n";
	print "\n";
	print "Where: -d cvsroot   Specifies cvs root, overrides 'CVSROOT' environment\n";
	print "                    variable and 'CVS/Root' file.\n";
	print "\n";
	print "       command      -l    shows list of all known tags\n";
	print "                    tag   shows list of files with this tag\n";
	print "\n";
	print "       module       Specifies module, overrides 'CVS/Repository' file.\n";
	print "\n";
	print "This command can be run from within a CVS sandbox. In this case both the\n";
	print "CVSROOT and CVS module can be overridden by the command line options. Note:\n";
	print "in this case the CVSROOT environment variable won't override the sandbox info.\n";
	print "\n";
	print "If not run from within a sandbox the CVSROOT and CVS module MUST be set on\n";
	print "the command line or, in the case of CSVROOT, via the environment.\n";
	print "\n";
	exit (1);
}

# Parse commandline
$::ROOT = ""; $::CMD = ""; $::MOD = "";
my $arg = shift @ARGV;
if ($arg eq "-d") {
	$::ROOT = shift @ARGV;
	if (!$::ROOT) {
		print "*** Error: -d option requires argument!\n\n";
		&Usage;
	}
} else {
	unshift @ARGV, $arg;
}
$::CMD = shift @ARGV;
$::MOD = shift @ARGV;
if (!$::CMD) { &Usage; }

# Check sandbox info
$::SBX_ROOT = "";
if (-r "CVS/Root") {
	open (INF, "<CVS/Root") || die "Failed to read CVS/Root file!\n";
	chop ($::SBX_ROOT = <INF>);
	close (INF);
}
$::SBX_MOD = "";
if (-r "CVS/Repository") {
	open (INF, "<CVS/Repository") || die "Failed to read CVS/Root file!\n";
	chop ($::SBX_MOD = <INF>);
	close (INF);
}
if ($::SBX_ROOT xor $::SBX_MOD) {
	print "*** Warning: ignoring incomplete CVS sandbox admin info!\n";
	$::SBX_ROOT = $::SBX_MOD = "";
}

# Decide what to do and how to do it
$::LOCAL = $::REMOTE = 0;
if ($::SBX_ROOT) {
	if ($::ROOT || $::MOD) {
		$::REMOTE = 1;
	} else {
		$::LOCAL = 1;
	}

} else {
	if (!$::ROOT) { $::ROOT = $ENV{CVSROOT}; }
	if ($::ROOT && $::MOD) {
		$::REMOTE = 1;
	} else {
		print "*** Error: CVSROOT and/or module not specified and not in sandbox!\n\n";
		&Usage;
	}
}
if ($::LOCAL && $::REMOTE) {
	print "### INTERNAL ERROR: DEVELOPER OUT OF COFFEE! ###\n\n";
	exit (42);
}
if ($::CMD eq "-l") { $::tag = ""; } else { $::tag = $::CMD; }
if (!$::ROOT) { $::ROOT = $::SBX_ROOT; }
if (!$::MOD) { $::MOD = $::SBX_MOD; }

# Now fetch and parse cvs info
if ($::LOCAL) {
	&FetchLocalInfo;
} else {
	&FetchRemoteInfo;
}

# Fetches sandbox cvs info with cvs status
sub FetchLocalInfo
{
	my (@STATUS, $aROOT, $state, $lc, $current);
	my ($fpath, $frpath, $fname, $fstatus, $ftag, $ftagrev);

	$state = $::found = 0;
	$current = $fpath = $frpath = $fname = $fstatus = $ftag = $ftagrev = "!UNINITIALIZED VARIABLE!";
	
	# Run cvs status and catch output
	open (INF, "cvs -q status -R -v |") || die "*** Error: failed to run cvs status command!\n";
	chop (@STATUS = <INF>);
	close (INF);
	
	# Determine actual on-system CVS root
	($aROOT) = $::ROOT =~ /^:[^:]+:[^\/]+(\/.*$)/;
	if (!defined ($aROOT)) { $aROOT = $::ROOT; }

	# Parse status
	undef (%::TAGL);
	for $lc (0 .. $#STATUS) {
		$_ = $STATUS[$lc];
		if ($state == 0) {
			if (/^File:/) {
				($fname, $fstatus) = /^File:\s+(\S+\s*\S+)\s+Status:\s+(\S+)/;
				$state = 1;
			}
			next;
		}
		if ($state == 1) {
			if (/^\s+Repository revision:/) {
				($frpath) = /(\/.*),v/;
				($fpath) = $frpath =~ /^$aROOT\/(.*)$/;
				push @::INFOL, ( $fpath );
				$current = $fpath;
				$::INFO{$current}->{rpath}  = $frpath;
				$::INFO{$current}->{name}   = $fname;
				$::INFO{$current}->{status} = $fstatus;
				$fpath = $frpath = $fname = $fstatus = "!UNINITIALIZED VARIABLE!";
				$state = 2;
			}
			next;
		}
		if ($state == 2) {
			if (/^\s+Existing Tags:/) {
				$state = 3;
			}
			next;
		}
		if (/^\s+\S+\s+\([^:]+:/) {
			($ftag, $ftagrev) = /^\s+(\S+)\s+\([^:]+:\s+([^\)]+)\)/;
			if (!$::tag) {
				$::TAGL{$ftag}++;
			} elsif ($ftag eq $::tag) {
				$::found++;
				$::INFO{$current}->{tag} = $ftag;
				$::INFO{$current}->{tagrev} = $ftagrev;
				$ftag = $ftagrev = "!UNINITIALIZED VARIABLE!";
			}
		} else { $state = 0; }
	}
	@STATUS = ();
}

# Fetches remote cvs info with cvs rlog
sub FetchRemoteInfo
{
	my (@STATUS, $aROOT, $state, $lc, $current);
	my ($fpath, $frpath, $ftag, $ftagrev);

	$state = $::found = 0;
	$current = $fpath = $frpath = $ftag = $ftagrev = "!UNINITIALIZED VARIABLE!";
	
	# Run cvs status and catch output
	open (INF, "cvs -d $::ROOT -q rlog $::MOD |") || die "*** Error: failed to run cvs rlog command!\n";
	chop (@STATUS = <INF>);
	close (INF);

	# Determine actual on-system CVS root
	($aROOT) = $::ROOT =~ /^:[^:]+:[^\/]+(\/.*$)/;
	if (!defined ($aROOT)) { $aROOT = $::ROOT; }

	# Parse status
	undef (%::TAGL);
	for $lc (0 .. $#STATUS) {
		$_ = $STATUS[$lc];
		if ($state == 0) {
			if (/^RCS file:/) {
				($frpath) = /^RCS file:\s+(.*),v/;
				($fpath) = $frpath =~ /^$aROOT\/(.*)$/;
				push @::INFOL, ( $fpath );
				$current = $fpath;
				$::INFO{$current}->{rpath}  = $frpath;
				$fpath = $frpath = "!UNINITIALIZED VARIABLE!";
				$state = 1;
			}
			next;
		}
		if ($state == 1) {
			if (/^symbolic names:/) {
				$state = 2;
			}
			next;
		}
		if ($state == 2) {
			if (!/^\s+\S+/) {
				$state = 0;
			} else {
				($ftag, $ftagrev) = /^\s+(\S+):\s*([\d\.]+)\s*$/;
				if (!$::tag) {
					$::TAGL{$ftag}++;
				} elsif ($ftag eq $::tag) {
					$::found++;
					$::INFO{$current}->{tag} = $ftag;
					$::INFO{$current}->{tagrev} = $ftagrev;
					$ftag = $ftagrev = "!UNINITIALIZED VARIABLE!";
				}
			}
			next;
		}
		print "### INTERNAL ERROR: DEVELOPER REALLY OUT OF COFFEE! ###\n\n";
		exit (42);
	}
	@STATUS = ();
}

# And finally print results
print "$0 - CVS tag and file lister version $::VERSION\n";
print "ID: $::cvs_ID\n\n";
if (!$::tag) {
	print "List of all known tags:\n\n";
	foreach $::key (sort {uc($a) cmp uc($b)} keys %::TAGL) {
		print "$::key\n";
	}
} else {
	print "Files with tag \"$::tag\":";
	if ($::found > 0) {
		print "\n\n";
	} else {
		print "  NONE\n";
	}
	for $::i (0 .. $#::INFOL) {
		if (!defined($::INFO{$::INFOL[$::i]}->{"tag"})) {
			next;
		}
		$::name = $::INFOL[$::i];
		$::status = $::INFO{$::name}->{"status"};
		if (!$::status) { $::status = "On-Server"; }
		$::tagrev = $::INFO{$::name}->{"tagrev"};
		printf "%10s %10s %s\n", ($::status, $::tagrev, $::name);
	}
}
print "\n";
