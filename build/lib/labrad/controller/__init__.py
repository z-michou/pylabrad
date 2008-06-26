import os
import hashlib
import random

import labrad
from labrad.config import ConfigFile
from labrad.util import maybeTimeout, simplejson
from labrad.wrappers import connectAsync

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.python.failure import Failure
from twisted.web import http, resource, static, server

HERE_DIR = os.path.split(os.path.abspath(__file__))[0]
#WEB_DIR = os.path.join(HERE_DIR, 'www', 'org.labrad.NodeController')
#WEB_DIR = 'U:/Matthew/projects/NodeController/www/org.labrad.NodeController'
WEB_DIR = 'U:/projects/NodeController/www/org.labrad.NodeController'

def _nodes(cxn):
    servers = sorted(cxn.servers.keys())
    return [s for s in servers if s.startswith('node')]

class JSONResource(resource.Resource):
    def __init__(self, cxn, func, *a, **kw):
        self.cxn = cxn
        self.func = func
        self.a = a
        self.kw = kw
        
    def render(self, request):
        @inlineCallbacks
        def doRequest():
            try:
                resp = yield self.func(self.cxn, request, *self.a, **self.kw)
                result = simplejson.dumps({'result': resp})
            except Exception, e:
                f = Failure(e)
                msg = f.getTraceback(elideFrameworkCode=1, detail='verbose')
                result = simplejson.dumps({'error': unicode(msg)})
            request.setHeader('content-type', 'application/json')
            request.setHeader('content-length', len(result))
            if request.method != 'HEAD':
                request.write(result)
            request.finish()
        doRequest()
        return server.NOT_DONE_YET
            
    
class JSONPuller(resource.Resource):
    def __init__(self, transport):
        self.transport = transport
        
    def render(self, request):
        #try:
            content = request.content.read()
            print content
            data = simplejson.loads(content)
            print data['id'], data['method'], data['args'], data['kw']
            self.transport.invokeMethod(data['id'], data['method'],
                                        *data['args'], **data['kw'])
            return ""
        #except Exception, e:
        #    return simplejson.dumps({'error': str(e)})
    
class JSONPusher(resource.Resource):
    def __init__(self, transport):
        self.transport = transport
        
    def render(self, request):
        d = self.transport.getResponses()
        d.addCallback(self._push, request)
        return server.NOT_DONE_YET
        
    def _push(self, result, request):
        request.setHeader('content-type', 'application/json')
        request.setHeader('content-length', len(result))
        request.write(result)
        print 'sending responses:', result
        print self.transport.responses
        print
        request.finish()
    
class JSONTransport(resource.Resource):
    def __init__(self):
        self.children = {}
        self.putChild('push', JSONPuller(self)) # client pushes, we pull
        self.putChild('pull', JSONPusher(self)) # client pulls, we push
        self.responses = []
        self.waiters = []
    
    def lookupMethod(self, name):
        return getattr(self, 'remote_' + name)
    
    def invokeMethod(self, id, name, *args, **kw):
        """Called when the client invokes a method on the server."""
        func = self.lookupMethod(name)
        d = defer.maybeDeferred(func, *args, **kw)
        d.addCallback(self._addResult, id)
        d.addErrback(self._addError, id)
    
    def getResponses(self):
        """Called by the client to get all pending responses.
        
        If no responses are waiting, return a deferred that will be
        fired later when responses become available.
        """
        if len(self.waiters):
            d = self.waiters.pop()
        else:
            d = defer.Deferred()
        if len(self.responses):
            reactor.callLater(0, d.callback, self._flushResponses())
        else:
            self.waiters.insert(0, d)
        return d
    
    def sendMessage(self, msg, *args, **kw):
        """Called by the server to push messages out to the client."""
        self._addResponse(message=msg, args=args, kw=kw)
    
    def _addResult(self, result, id):
        self._addResponse(id=id, result=result)
    
    def _addError(self, failure, id):
        self._addResponse(id=id, error=failure.getBriefTraceback())
    
    def _addResponse(self, **kw):
        self.responses.append(kw)
        if len(self.waiters):
            d = self.waiters.pop()
            d.callback(self._flushResponses())
    
    def _flushResponses(self):
        resp = simplejson.dumps(self.responses)
        self.responses = []
        return resp
        
class NodeProxy(JSONTransport):
    @inlineCallbacks
    def remote_available_servers(self, *args, **kw):
        cxn = self.cxn
        resp = yield DeferredList([cxn[node].available_servers() for node in _nodes(cxn)])
        avail = set()
        for success, result in resp:
            if success:
                avail.update(result)
        returnValue(sorted(unicode(name) for name in avail))
        
    def remote_list_servers(self, *args, **kw):
        return [unicode(s) for s in self.cxn.servers.keys()]
        
    def remote_list_nodes(self, *args, **kw):
        return [unicode(s) for s in _nodes(self.cxn)]
        
    @inlineCallbacks
    def remote_list_both(self, *args, **kw):
        cxn = self.cxn
        servers = yield self.remote_available_servers(*args, **kw)
        nodes = yield self.remote_list_nodes(*args, **kw)
        
        status_dict = {}
        running = yield DeferredList([cxn[node].running_servers() for node in _nodes(cxn)])
        for (success, result), node in zip(running, _nodes(cxn)):
            if success:
                status_dict[node] = result
         
        status = []
        for server in servers:
            row = []
            for node in nodes:
                if node not in status_dict:
                    row.append([unicode(server), False])
                else:
                    found = False
                    for running_server, instance in status_dict[node]:
                        if running_server == server:
                            row.append([unicode(instance), True])
                            found = True
                            break
                    if not found:
                        row.append([unicode(server), False])
            status.append(row)
        
        returnValue([servers, nodes, status])
    
    @inlineCallbacks
    def remote_iplists(self, *args, **kw):
        cxn = self.cxn
        p = cxn.manager.packet()
        p.whitelist()
        p.blacklist()
        resp = yield p.send()
        returnValue((sorted(resp.whitelist), sorted(resp.blacklist)))
    
    def remote_blacklist(self, address):
        return self.cxn.manager.blacklist(str(address))
    
    def remote_whitelist(self, address):
        return self.cxn.manager.whitelist(str(address))
    
    def remote_start(self, node, server):
        return self.cxn[node].start(str(server), context=self.cxn.context())
        
    def remote_restart(self, node, server):
        return self.cxn[node].restart(str(server), context=self.cxn.context())
        
    def remote_stop(self, node, server):
        return self.cxn[node].stop(str(server), context=self.cxn.context())
        
    
theTransport = NodeProxy()
from twisted.internet.task import LoopingCall
def doCall():
    from datetime import datetime
    theTransport.sendMessage('timer', str(datetime.now()))
#lc = LoopingCall(doCall)
#lc.start(20, now=False)
    
class NodeAPI(resource.Resource):
    reconnectDelay = 10
    
    def _connect(self):
        d = connectAsync(self.host, self.port, name='Web Interface Client')
        d.addCallbacks(self._connectionSucceeded, self._connectionFailed)

    def _connectionSucceeded(self, cxn):
        try:
            cxn.onShutdown().addBoth(self._connectionFailed)
            self.cxn = cxn
            self.connected = True
            print 'Connected to manager %s:%d.' % (self.host, self.port)
        except Exception, e:
            print e
            print 'Something went wrong in connection.'
            self._reconnect()

    def _connectionFailed(self, reason):
        print reason.getErrorMessage()
        self._reconnect()
        
    def _reconnect(self):
        self.cxn = None
        print 'Will try to reconnect in %d seconds...' % self.reconnectDelay
        reactor.callLater(self.reconnectDelay, self._connect)
    
    def getChild(self, path, request):
        if path == 'transport':
            theTransport.cxn = self.cxn
            return theTransport
        func = getattr(self, 'remote_' + path)
        return JSONResource(self.cxn, func)
        
    @inlineCallbacks
    def remote_available_servers(self, cxn, request):
        resp = yield DeferredList([cxn[node].available_servers() for node in _nodes(cxn)])
        avail = set()
        for success, result in resp:
            if success:
                avail.update(result)
        returnValue(sorted(unicode(name) for name in avail))
        
    def remote_list_servers(self, cxn, request):
        return [unicode(s) for s in cxn.servers.keys()]
        
    def remote_list_nodes(self, cxn, request):
        return [unicode(s) for s in _nodes(cxn)]
        
    @inlineCallbacks
    def remote_list_both(self, cxn, request):
        servers = yield self.remote_available_servers(cxn, request)
        nodes = yield self.remote_list_nodes(cxn, request)
        
        status_dict = {}
        running = yield DeferredList([cxn[node].running_servers() for node in _nodes(cxn)])
        for (success, result), node in zip(running, _nodes(cxn)):
            if success:
                status_dict[node] = result
         
        status = []
        for server in servers:
            row = []
            for node in nodes:
                if node not in status_dict:
                    row.append([unicode(server), False])
                else:
                    found = False
                    for running_server, instance in status_dict[node]:
                        if running_server == server:
                            row.append([unicode(instance), True])
                            found = True
                            break
                    if not found:
                        row.append([unicode(server), False])
            status.append(row)
        
        returnValue([servers, nodes, status])
    
    @inlineCallbacks
    def remote_iplists(self, cxn, request):
        p = cxn.manager.packet()
        p.whitelist()
        p.blacklist()
        resp = yield p.send()
        returnValue((sorted(resp.whitelist), sorted(resp.blacklist)))
    
    def remote_blacklist(self, cxn, request):
        address = request.args['address'][0]
        return cxn.manager.blacklist(address)
    
    def remote_whitelist(self, cxn, request):
        address = request.args['address'][0]
        return cxn.manager.whitelist(address)
    
    def remote_start(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].start(server)
        
    def remote_restart(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].restart(server)
        
    def remote_stop(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].stop(server)

class DigestAuthRequest(server.Request):
    def process(self):
        "Process a request."
        if self.checkAuthorization():
            server.Request.process(self)
        else:
            self.sendUnauthorizedResponse()
        
    def checkAuthorization(self):
        auth = self.getHeader('Authorization')
        if auth is None:
            return False
        auth = auth.strip()
        if not auth.startswith('Digest'):
            return False
        try:
            auth = [s.split('=', 1) for s in auth[6:].split(',')]
            auth = dict([s.strip().strip('"') for s in item] for item in auth)
            
            def hash(*strs):
                m = hashlib.md5()
                m.update(':'.join(strs))
                return m.hexdigest()
    
            user = auth['username']
            status = self.channel.site.users[user]
            #if self.path == '/__logout__':
            #    status['logged_in'] = False
            #    return False
            pw = status['pw']
            ha1 = hash(user, auth['realm'], pw)
            ha2 = hash(self.method, auth['uri'])
            response = hash(ha1, auth['nonce'], auth['nc'],
                            auth['cnonce'], auth['qop'], ha2)
            
            return response == auth['response']
        except Exception, e:
            print e
        return False
        
    def sendUnauthorizedResponse(self):
        self.setResponseCode(http.UNAUTHORIZED)

        # set various default headers
        self.setHeader('server', server.version)
        self.setHeader('date', http.datetimeToString())
        self.setHeader('content-type', "text/html")

        realm = "LabRAD Controller"
        nonce = generateNonce()
        opaque = generateNonce()
        msg = '''Digest realm="%s", qop="auth", nonce="%s", opaque="%s"'''
        self.setHeader('WWW-Authenticate', msg % (realm, nonce, opaque))
        self.write('<html><h1>Invalid username/password!</h1></html>')
        self.finish()

def generateNonce():
    return ''.join(random.choice('0123456789abcdef') for _ in range(32))
        
def makeNodeControllerSite(host, port):
    try:
        passFile = ConfigFile('controller.ini')
    except:
        passFile = ConfigFile('controller-template.ini')

    root = static.File(WEB_DIR)
    root.indexNames = ['NodeController.html']
    api = NodeAPI()
    api.host = host
    api.port = port
    api._connect()
    root.putChild('api', api)
    site = server.Site(root)
    site.requestFactory = DigestAuthRequest
        
    site.users = {}
    for section in passFile.sections():
        try:
            user = passFile.get(section, 'username')
            pw = passFile.get(section, 'password')
            site.users[user] = {'pw': pw, 'logged_in': True}
        except Exception, e:
            print e
    return site

if __name__ == '__main__':
    from twisted.internet import reactor
    site = makeNodeControllerSite('localhost', 7682)
    reactor.listenTCP(7667, site)
    reactor.run()