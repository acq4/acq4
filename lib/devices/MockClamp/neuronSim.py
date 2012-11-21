import numpy as np
import pickle
import sys, os

## change working directory so neuron can find compiled mod files.
wd = os.getcwd()
path = os.path.join(os.path.dirname(__file__), 'neuron')
print "chdir", path
os.chdir(path)
from neuron import h
import neuron
os.chdir(wd)

#opts = pickle.loads(sys.stdin.read())
#opts = {
    #'data': np.zeros(1000),
    #'dt': 1e-4,
#}
#opts['data'][600:700] = 100e-12
#sys.stderr.write("%f, %f, %f" % (opts['data'].min(), opts['data'].max(), opts['dt']))
#sys.stdout.write(pickle.dumps(opts['data']))


#data = opts['data']  ## convert to nA
#dt = opts['dt']*1e3  ## convert to ms
#leadTime = 1  #1ms for membrane to settle

h.celsius = 22

soma = h.Section()
soma.insert('hh')
soma.insert('pas')
soma.insert('hcno')
soma.L = 20
soma.diam = 20
soma(0.5).pas.g = 2e-5
soma(0.5).hcno.gbar = 15e-4

ic = h.IClamp(soma(0.5))
ic.dur = 1e9
ic.delay = 0
icRec = h.Vector()
icRec.record(soma(0.5)._ref_v)

vc = h.SEClamp(soma(0.5))
vc.dur1 = 1e9
vc.rs = 10.
#vc.amp1 = 0
#vc.dur2 = 1e9
vcrs = vc.rs
vcRec = h.Vector()
vcRec.record(vc._ref_i)

t = 0
    
def run(cmd):
    global t, soma, ic, vc, icRec, vcRec, vcrs
    icRec.clear()
    vcRec.clear()
    
    dt = cmd['dt'] * 1e3  ## convert s -> ms
    h.dt = dt
    data = cmd['data']
    mode = cmd['mode']
    #print "data:", data.min(), data.max()

    #times = h.Vector(np.linspace(h.t, h.t+len(data)*dt, len(data)))
    #print "times:", times.min(), times.max()
    if mode == 'ic':
        #ic.delay = h.t
        ic.delay = 0
        vc.rs = 1e9
        im = h.Vector(data * 1e9)
        im.play(ic._ref_amp, dt)

    elif mode == 'vc':
        #vc.amp1 = data[0]
        vc.rs = vcrs
        ic.delay = 1e9
        #vc.dur1 = h.t
        vm = h.Vector(data * 1e3)
        vm.play(vc._ref_amp1, dt)
        
    else:
        sys.stderr.write("Unknown mode '%s'" % sys.argv[1])
        raise Exception("Unknown mode '%s'" % sys.argv[1])

    #t2 = t + dt * (len(data)+2)
    #print "run until:", t2
    neuron.init()
    #neuron.finitialize(-65)
    neuron.run(dt * (len(data)+2))
    #neuron.run(t2)
    #t = t2

    #print len(out), out
    #out = np.array(out)[:len(data)]

    if mode == 'ic':
        out = np.array(icRec)[:len(data)] * 1e-3 + np.random.normal(size=len(data), scale=0.3e-3)
    elif mode == 'vc':
        out = np.array(vcRec)[:len(data)] * 1e-9 + np.random.normal(size=len(data), scale=3.e-12)
    
    return out

#sys.stdout.write(pickle.dumps(out))
#print np.array(vm)





if __name__ == '__main__':
    data = np.zeros((1000))
    data[200:700] += 10e-9
    opts = {
        'mode': 'ic',
        'dt': 1e-4,
        'data': data
    }
    
    print run(opts)
    
    
    
    