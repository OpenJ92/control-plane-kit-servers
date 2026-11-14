#!/usr/bin/perl
# POSIX-only local child supervision and bounded pipe capture. Never reaps an
# owned child until every possible signal to its PID/group has been cancelled.
use strict;
use warnings;
use POSIX qw(SIG_BLOCK SIG_SETMASK SIGCHLD SIGALRM SIGTERM SIGINT SIGHUP
             sigprocmask sigsuspend setpgid);

my $mode = shift @ARGV // '';
if ($mode eq 'capture') {
    my $limit = shift @ARGV // '';
    exit 125 unless $limit =~ /^\d+$/ && $limit > 0 && $limit <= 1048576 && !@ARGV;
    binmode STDIN;
    binmode STDOUT;
    my $bytes = '';
    while (length($bytes) <= $limit) {
        my $part = '';
        my $count = sysread(STDIN, $part, $limit + 1 - length($bytes));
        exit 125 unless defined $count;
        last if $count == 0;
        $bytes .= $part;
        exit 125 if index($bytes, "\0") >= 0 || length($bytes) > $limit;
    }
    # A non-newline terminator prevents shell substitution from changing the
    # captured bytes. It is removed only after byte/NUL validation above.
    print STDOUT $bytes, "\x01";
    exit 0;
}

my $seconds = shift @ARGV // '';
exit 125 unless ($mode eq 'process' || $mode eq 'group') &&
    $seconds =~ /^\d+$/ && $seconds >= 1 && $seconds <= 300 &&
    (shift @ARGV // '') eq '--' && @ARGV;
my @signals = (SIGCHLD, SIGALRM, SIGTERM, SIGINT, SIGHUP);
my $blocked = POSIX::SigSet->new(@signals);
my $previous = POSIX::SigSet->new();
exit 125 unless defined sigprocmask(SIG_BLOCK, $blocked, $previous);
my $waiting = POSIX::SigSet->new();
exit 125 unless defined sigprocmask(SIG_BLOCK, POSIX::SigSet->new(), $waiting);
$waiting->delset($_) for @signals;
my ($child_done, $tick, $interrupted) = (0, 0, 0);
$SIG{CHLD} = sub { $child_done = 1; }; # Deliberately no wait/reap here.
$SIG{ALRM} = sub { $tick = 1; };
$SIG{TERM} = $SIG{INT} = $SIG{HUP} = sub { $interrupted = 1; };
my $child = fork();
exit 125 unless defined $child;
if ($child == 0) {
    exit 125 if $mode eq 'group' && setpgid(0, 0) != 0;
    $SIG{$_} = 'DEFAULT' for qw(CHLD ALRM TERM INT HUP);
    sigprocmask(SIG_SETMASK, $previous);
    exec { $ARGV[0] } @ARGV or POSIX::_exit(125);
}
setpgid($child, $child) if $mode eq 'group';
my $target = $mode eq 'group' ? -$child : $child;
my ($cleaning, $expired) = (0, 0);
if ($seconds == 1) { $tick = 1; } else { alarm($seconds - 1); }
while (1) {
    if ($interrupted || $tick) {
        $interrupted = $tick = 0;
        if (!$cleaning) {
            $expired = $cleaning = 1;
            kill SIGTERM, $target;
            alarm 1;
        } else {
            kill 9, $target;
            alarm 0;
            last;
        }
    }
    if ($child_done && !$cleaning) {
        alarm 0;
        if ($mode eq 'process') { last; }
        # The unreaped group leader reserves the group identity while any
        # invocation-owned descendants finish, even when the leader is done.
        $cleaning = 1;
        kill SIGTERM, $target;
        alarm 1;
    }
    sigsuspend($waiting);
}
alarm 0; # Signals are still blocked. There is no signal path after this reap.
my $waited;
do { $waited = waitpid($child, 0); } while ($waited < 0 && $!{EINTR});
exit 125 if $waited != $child;
my $status = $?;
exit 124 if $expired;
exit(($status & 127) ? 128 + ($status & 127) : ($status >> 8));
