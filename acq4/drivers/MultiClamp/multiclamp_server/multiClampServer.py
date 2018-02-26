from __future__ import print_function
import socket, threading, sys, re, types
from . import axonmc



def main():
    ## Use 34567 as default port
    if len(sys.argv) < 2:
        port = 34567
    else:
        port = int(sys.argv[1])
        
    ## Mutex to serialize requests to multiclamp
    lock = threading.Lock()
    
    mc = axonmc.MULTICLAMP
    
    ## Set up network socket and listen for connections
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', port))
    s.listen(1)
    print("Listening on port", port)
    while True:
        conn, addr = s.accept()
        print("Connected to", addr[0])
        t = WorkThread(conn, addr, mc, lock)
        t.start()
    
    
class WorkThread(threading.Thread):
    def __init__(self, conn, addr, mc, lock):
        self.conn = conn
        self.addr = addr
        self.lock = lock
        self.mc = mc
        threading.Thread.__init__(self)
        
    def run(self):
        while True:
            cmd = self.readline()
            if cmd is None:
                break
            print(self.addr[0], "req:", cmd[:-1])
            try:
                resp = [1] + self.processCmd(cmd)
            except:
                resp = [0] + list(sys.exc_info()[1].args)
            resp = ','.join(map(str, resp))
            print(self.addr[0], "response:", resp)
            self.conn.sendall(resp + '\n')
        self.conn.close()
        print("Closing connection to", self.addr[0])
                
    def processCmd(self, cmd):
        ## Parse out function name and arguments
        m = re.match(r'(\S+)\((.*)\)', cmd)
        if m is None:
            raise Exception("Command must be in the form 'function(arguments)'")
        fn = m.groups()[0]
        argstr = m.groups()[1]
        strargs = re.split(r'\s*,\s*', argstr)
        
        ## Guess types for arguments
        args = []
        for a in strargs:
            if a.lower() == 'true':
                args.append(True)
            elif a.lower() == 'false':
                args.append(False)
            elif re.match(r'[a-zA-Z]', a):
                args.append(a)
            elif a == '':
                pass
            else:
                if '.' in a:
                    args.append(float(a))
                else:
                    args.append(int(a))
        print("%s call: %s(%s)" % (self.addr[0], fn, str(args)))
        
        ## Run function
        self.lock.acquire()
        try:
            ret = getattr(self.mc, fn)(*args)
        except:
            self.lock.release()
            raise
        self.lock.release()
        
        if not isinstance(ret, list):
            ret = [ret]
        return ret

    def readline(self):
        l = ''
        while True:
            c = self.conn.recv(1)
            if c == '':
                if len(l) > 0:
                    print(self.addr[0], "Connection closing with incomplete command:", l)
                return None
            l += c
            if l[-1] == '\n':
                return l


main()