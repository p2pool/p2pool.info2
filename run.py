from __future__ import division

import sys
import os
import json
import urllib
import time

from p2pool.bitcoin import data as bitcoin_data
from p2pool.util import math as util_math

datadir = sys.argv[1]
p2pool_base_url = sys.argv[2]

def get(blah):
    f = urllib.urlopen(p2pool_base_url.rstrip('/') + '/' + blah)
    d = f.read()
    f.close()
    return json.loads(d)

def _atomic_read(filename, default):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except IOError, e:
        if e.errno != errno.ENOENT:
            raise
    try:
        with open(filename + '.new', 'rb') as f:
            return f.read()
    except IOError, e:
        if e.errno != errno.ENOENT:
            raise
    return default

def _atomic_write(filename, data):
    with open(filename + '.new', 'wb') as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except:
            pass
    try:
        os.rename(filename + '.new', filename)
    except: # XXX windows can't overwrite
        os.remove(filename)
        os.rename(filename + '.new', filename)

# read old

old_blocks = json.loads(_atomic_read(
    os.path.join(datadir, 'blocks'),
    '[]',
))
old_stats = json.loads(_atomic_read(
    os.path.join(datadir, 'stats'),
    '{rates: [], maxRate: 0, users: [], maxUsers: 0}',
))


# update
#print stats

web_local_stats = get('local_stats')
web_global_stats = get('global_stats')
web_users = get('users')
web_current_payouts = get('current_payouts')

difficulty = bitcoin_data.target_to_difficulty(
    bitcoin_data.average_attempts_to_target(web_local_stats['attempts_to_block']))
users = [dict(
    Hashrate=util_math.format(int(frac * web_global_stats['pool_hash_rate'] + 1/2), add_space=True) + 'H/s',
    Address=addr,
) for addr, frac in sorted(web_users.iteritems(), key=lambda (k, v): -v)]

payouts = [dict(
    Address=addr,
    Payment=amt,
) for addr, amt in sorted(web_current_payouts.iteritems(), key=lambda (k, v): -v)]


stats = dict(
    rates=old_stats['rates'] + [[time.time(), web_global_stats['pool_hash_rate']/1e9]],
    maxRate=max(old_stats['maxRate'], web_global_stats['pool_hash_rate']/1e9),
    users=old_stats['users'] + [[time.time(), len(web_users)]],
    maxUsers=max(old_stats['maxUsers'], len(web_users)),
)

blocks = old_blocks # XXX

# write

_atomic_write(os.path.join(datadir, 'blocks'), json.dumps(blocks))
_atomic_write(os.path.join(datadir, 'difficulty'), json.dumps(difficulty))
#_atomic_write(os.path.join(datadir, 'donations'), json.dumps(donations))
_atomic_write(os.path.join(datadir, 'payouts'), json.dumps(payouts))
_atomic_write(os.path.join(datadir, 'stats'), json.dumps(stats))
_atomic_write(os.path.join(datadir, 'users'), json.dumps(users))
