from __future__ import division

import sys
import os
import json
import urllib
import time
import errno
import base64

from twisted.internet import defer, reactor
from twisted.web import client

from p2pool.bitcoin import data as bitcoin_data, networks
from p2pool import data as p2pool_data
from p2pool.util import math as util_math, jsonrpc

net = networks.nets['bitcoin']

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

@defer.inlineCallbacks
def get_blocks(b, n):
    h = yield b.rpc_getbestblockhash()
    res = []
    for i in xrange(n):
        block_data = yield b.rpc_getblock(h, False)
        block_data2 = yield b.rpc_getblock(h)
        block = bitcoin_data.block_type.unpack(block_data.decode('hex'))
        res.append(dict(
            block=block,
            height=block_data2['height'],
            gentx_hash=bitcoin_data.hash256(bitcoin_data.tx_type.pack(block['txs'][0])),
        ))
        h = '%064x' % (block['header']['previous_block'],)
    defer.returnValue(res)

def blockchain(cmd):
    return client.getPage('http://blockchain.info/' + cmd).addCallback(json.loads)

@defer.inlineCallbacks
def get_blocks2(n):
    height = yield blockchain('q/getblockcount')
    
    res = []
    
    for i in xrange(n):
        x = yield blockchain('block-height/%i?format=json' % (height - i,))
        for block in x['blocks']:
            #print block
            header = dict(
                version=block['ver'],
                previous_block=int(block['prev_block'], 16),
                merkle_root=int(block['mrkl_root'], 16),
                timestamp=block['time'],
                bits=bitcoin_data.FloatingInteger(block['bits']),
                nonce=block['nonce'],
            )
            assert bitcoin_data.hash256(bitcoin_data.block_header_type.pack(header)) == int(block['hash'], 16)
            
            
            # there seems to be no way to get the raw transaction
            # from blockchain.info (?format=hex doesn't work for
            # coinbase transctions ): so instead fake it
            
            
            txs = [dict(
                version=tx['ver'],
                tx_ins=[dict(
                    previous_output=None,
                    script='',
                    sequence=0,
                ) for tx_in in tx['inputs']],
                tx_outs=[dict(
                    value=tx_out['value'],
                    script='\x6a' + 'blah'*100 if tx_out['type'] == -1 else
                        p2pool_data.DONATION_SCRIPT if tx_out['addr'] == bitcoin_data.script2_to_address(p2pool_data.DONATION_SCRIPT, net) else
                        bitcoin_data.pubkey_hash_to_script2(bitcoin_data.address_to_pubkey_hash(tx_out['addr'], net)),
                ) for tx_out in tx['out']],
                lock_time=0,
            ) for tx in block['tx']]
            
            #print txs[0]
            
            # fails because we don't have coinbase script ):
            #assert bitcoin_data.hash256(bitcoin_data.tx_type.pack(txs[0])) == block['tx'][0]['hash']
            
            block2 = dict(header=header, txs=txs)
            
            res.append(dict(
                block=block2,
                height=block['height'],
                gentx_hash=int(block['tx'][0]['hash'], 16),
            ))
    
    defer.returnValue(res)
    
    


@defer.inlineCallbacks
def main():
    datadir = sys.argv[1]
    p2pool_base_url = sys.argv[2]
    b = jsonrpc.HTTPProxy(sys.argv[3], dict(
        Authorization='Basic ' + base64.b64encode(
            sys.argv[4] + ':' + sys.argv[5]
        ),
    ), timeout=30)

    def get(blah):
        f = urllib.urlopen(p2pool_base_url.rstrip('/') + '/' + blah)
        d = f.read()
        f.close()
        return json.loads(d)

    # read old

    old_blocks = json.loads(_atomic_read(
        os.path.join(datadir, 'blocks'),
        '[]',
    ))
    old_stats = json.loads(_atomic_read(
        os.path.join(datadir, 'stats'),
        '{"rates": [], "maxRate": 0, "users": [], "maxUsers": 0}',
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

    def update_timeseries(x, value, now_time):
        lastlast_time = x[-2][0]
        last_time = x[-1][0]
        next_time = last_time + (last_time - lastlast_time)
        
        if abs(now_time - last_time) < abs(now_time - next_time):
            # update last
            old_value = x[-1][1]
            old_weight = x[-1][2] if len(x[-1]) >= 3 else 1e9
            return x[:-1] + [
                [last_time, (old_value * old_weight + value)/(old_weight + 1), old_weight + 1]
            ]
        else:
            # start next
            return x + [
                [next_time, value, 1]
            ]

    stats = dict(
        rates=update_timeseries(old_stats['rates'], web_global_stats['pool_hash_rate']/1e9, time.time()*1e3),
        maxRate=max(old_stats['maxRate'], web_global_stats['pool_hash_rate']/1e9),
        users=update_timeseries(old_stats['users'], len(web_users), time.time()*1e3),
        maxUsers=max(old_stats['maxUsers'], len(web_users)),
    )

    blocks = list(old_blocks)
    blocks_dict = dict((block['Id'], block) for block in blocks)
    assert len(blocks_dict) == len(blocks)
    for block_data in list((yield get_blocks(b, 400))):# + list((yield get_blocks2(200))):
        block = block_data['block']
        
        txouts = block['txs'][0]['tx_outs']
        
        if len(txouts) < 25: continue
        if not txouts[-1]['script'].startswith('\x6a'): continue
        if len(txouts[-1]['script']) < 33: continue
        if txouts[-1]['value'] != 0: continue
        if txouts[-2]['script'] != p2pool_data.DONATION_SCRIPT: continue
        
        hash_str = '%064x' % bitcoin_data.hash256(bitcoin_data.block_header_type.pack(block['header']))
        print hash_str
        
        if hash_str not in blocks_dict:
            print 'inserted'
            x = dict(
                Id=hash_str,
                PrevBlock='%064x' % block['header']['previous_block'],
                GenerationTxHash='%064x' % block_data['gentx_hash'],
                BlockHeight=block_data['height'],
                Difficulty=bitcoin_data.target_to_difficulty(block['header']['bits'].target),
                Timestamp=block['header']['timestamp'],
                IsOrphaned=None, # XXX
            )
            blocks.append(x)
            blocks_dict[hash_str] = x
    blocks.sort(key=lambda x: -x['Timestamp'])

    # write

    _atomic_write(os.path.join(datadir, 'blocks_5'), json.dumps(blocks[:5]))
    _atomic_write(os.path.join(datadir, 'blocks_100'), json.dumps(blocks[:100]))
    _atomic_write(os.path.join(datadir, 'blocks'), json.dumps(blocks))
    _atomic_write(os.path.join(datadir, 'difficulty'), json.dumps(difficulty))
    #_atomic_write(os.path.join(datadir, 'donations'), json.dumps(donations))
    _atomic_write(os.path.join(datadir, 'payouts'), json.dumps(payouts))
    _atomic_write(os.path.join(datadir, 'stats'), json.dumps(stats))
    _atomic_write(os.path.join(datadir, 'users'), json.dumps(users))

def f(x):
    reactor.stop()
    return x
reactor.callWhenRunning(lambda: main().addBoth(f))
reactor.run()
