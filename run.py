from __future__ import division

import json

from twisted.web import static, server, resource, util
from twisted.internet import reactor

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

class JSONFuncResource(resource.Resource):
    def __init__(self, func):
        resource.Resource.__init__(self)
        self.func = func
    
    def render_GET(self, request):
        request.setHeader('Content-Type', 'application/json')
        return json.dumps(self.func())


with open('stats', 'rb') as f:
    stats = json.load(f)
    # rates, maxRate, users, maxUsers


web_root = static.File('static')
web_root.putChild('stats', JSONFuncResource(lambda: stats))

reactor.listenTCP(8080, server.Site(web_root))

reactor.run()
