from __future__ import print_function
"""
Use NEURON to simulate a simple cell for testing with MockClamp
"""
import numpy as np
import sys, os
from neuron import h
import neuron
import urllib.request
import zipfile

h.celsius = 34
vrest = -70e-3  # updated later

model_base_path = os.path.join(os.path.dirname(__file__), 'models')

def load_mechanisms(path):
    for name in ('i386', 'x86_64'):
        mechlib = os.path.join(path, name + '/.libs/libnrnmech.so')
        print("NEURON load:", mechlib)
        if os.path.isfile(mechlib):
            h.nrn_load_dll(mechlib)


def load_default():
    global soma
    # try to load extra mechanisms
    load_mechanisms(os.path.dirname(__file__))

    soma = h.Section()
    soma.insert('hh')
    soma.insert('pas')
    #soma.insert('hcno')
    soma.L = 20
    soma.diam = 20
    soma(0.5).pas.g = 2e-5
    #soma(0.5).hcno.gbar = 15e-4

    setup_clamp()


def load_allen(model_id):
    """Downloads and loads an Allen Cell Types model into NEURON

    Requires the AllenSDK package to be installed. The model will be downloaded
    and compiled if it has not been downloaded before.
    """
    global soma, h
    import allensdk.model.biophysical as allensdk_model_biophysical
    from allensdk.model.biophysical.runner import run, load_description
    from allensdk.model.biophysical.utils import create_utils

    lib_path = os.path.dirname(allensdk_model_biophysical.__file__)
    hoc_file = os.path.join(lib_path, 'cell.hoc')
    if not os.path.exists(hoc_file):
        url = "https://raw.githubusercontent.com/AllenInstitute/AllenSDK/master/allensdk/model/biophysical/cell.hoc"
        urllib.request.urlretrieve(url, hoc_file)

    model_path = os.path.join(model_base_path, str(model_id))
    if not os.path.exists(model_path):
        try:
            if not os.path.exists(model_base_path):
                os.mkdir(model_base_path)
            os.mkdir(model_path)
            url = 'http://celltypes.brain-map.org/neuronal_model/download/%d' % model_id
            print("Downloading model %d from %s" % (model_id, url))
            zip_path = os.path.join(model_path, 'model.zip')
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(model_path)
            os.remove(zip_path)
            os.system(f'cd {model_path}; nrnivmodl ./modfiles')
        except Exception as e:
            # remove the directory and all files inside
            import shutil
            shutil.rmtree(model_path)
            raise e

    load_mechanisms(model_path)

    os.chdir(model_path)
    manifest_file = os.path.join(model_path, 'manifest.json')
    desc = load_description({'manifest_file': manifest_file})

    utils = create_utils(desc)
    morphology_path = desc.manifest.get_path('MORPHOLOGY').encode('ascii', 'ignore')
    morphology_path = morphology_path.decode("utf-8")
    utils.generate_morphology(morphology_path)
    utils.load_cell_parameters()

    h = utils.h
    soma = h.soma[0]

    setup_clamp()


def setup_clamp():
    global soma, ic, vc, syn, icRec, vcRec, vcrs, vrest
    ic = h.IClamp(soma(0.5))
    ic.dur = 1e9
    ic.delay = 0
    icRec = h.Vector()
    icRec.record(soma(0.5)._ref_v)

    vc = h.SEClamp(soma(0.5))
    vc.dur1 = 1e9
    vc.rs = 5  # Rs, in megohms
    #vc.amp1 = 0
    #vc.dur2 = 1e9
    vcrs = vc.rs
    vcRec = h.Vector()
    vcRec.record(vc._ref_i)

    # add an alpha synapse, reversal -7 mV
    # note that synaptic current will appear in the SEClamp or IClamp
    syn = h.AlphaSynapse(soma(0.5))


def ss_init(t0=-1e3, dur=1e2, dt=0.025):
    """Initialize to steady state.  
    Executes as part of h.finitialize()
    Appropriate parameters depend on your model
    t0 -- how far to jump back (should be < 0)
    dur -- time allowed to reach steady state
    dt -- initialization time step

    from https://neuron.yale.edu/neuron/docs/custom-initialization
    """
    h.t = t0
    # save CVode state to restore; initialization with fixed dt
    old_cvode_state = h.cvode.active()
    h.cvode.active(False)
    h.dt = dt
    while (h.t < t0 + dur): 
        h.fadvance()
    # restore cvode active/inactive state if necessary
    h.cvode.active(old_cvode_state)
    h.t = 0
    if h.cvode.active():
        h.cvode.re_init()
    else:
        h.fcurrent()
    h.frecord_init()

# calls to finitialize will call ss_init
# fih = h.FInitializeHandler(ss_init)


_rmp_cache = {}
def rmp_at_ic(icHolding):
    global _rmp_cache, h, ic, soma
    if icHolding in _rmp_cache:
        return _rmp_cache[icHolding]
    h.dt = 1
    ic.amp = icHolding * 1e9
    vc.rs = 1e9
    neuron.init()
    h.finitialize(vrest * 1e3)
    h.run(2000)
    rmp = soma(0.5).v
    _rmp_cache[icHolding] = rmp
    print(f"RMP: {icHolding*1e12}pA: {rmp}mV")
    return rmp


def run(cmd):
    global h, soma, ic, vc, syn, icRec, vcRec, vcrs

    # run a short simulation to settle the model
    # neuron.init()
    # settle_time = 1000 # ms
    # h.dt = 1e-3
    # if cmd['mode'] in ('IC', 'I=0'):
    #     if cmd['mode'] == 'I=0':
    #         ic.amp = 0
    #     else:
    #         ic.amp = cmd['icHolding'] * 1e9
    # elif cmd['mode'] == 'VC':
    #     vc.amp1 = cmd['vcHolding']
    # h.finitialize(vrest * 1e3)
    # h.run(settle_time)

    
    dt = cmd['dt'] * 1e3  ## convert s -> ms
    h.dt = dt
    data = cmd['data']
    mode = cmd['mode']


    # add extra data to let model settle
    extra = 100  # ms
    n_extra = int(extra / dt)
    data = np.empty(n_extra + len(data), dtype=data.dtype)
    data[n_extra:] = cmd['data']
    if mode == 'I=0':
        data[:n_extra] = 0
    elif mode == 'IC':
        data[:n_extra] = cmd['icHolding']
    elif mode == 'VC':
        data[:n_extra] = cmd['vcHolding']


    #print "data:", data.min(), data.max()

    #times = h.Vector(np.linspace(h.t, h.t+len(data)*dt, len(data)))
    #print "times:", times.min(), times.max()
    if mode == 'IC':
        #ic.delay = h.t
        ic.delay = 0
        vc.rs = 1e9
        im = h.Vector(data * 1e9)
        im.play(ic._ref_amp, dt)

    elif mode == 'VC':
        #vc.amp1 = data[0]
        ic.amp = 0
        vc.rs = vcrs
        ic.delay = 1e9
        #vc.dur1 = h.t
        vm = h.Vector(data * 1e3)
        vm.play(vc._ref_amp1, dt)

        syn.onset = 400. #ms
        syn.tau = 1.5 # ms
        syn.gmax = 0.04 # umho
        syn.e = -7.0 # mV
        #syn.i --- nA
        
    else:
        raise Exception("Unknown mode '%s'" % mode)

    #t2 = t + dt * (len(data)+2)
    #print "run until:", t2

    if mode == 'I=0':
        # vinit = rmp_at_ic(0)
        vinit = -75
        ic.amp = 0
    elif mode == 'IC':
        # vinit = rmp_at_ic(cmd['icHolding'])
        vinit = -75
        ic.amp = cmd['icHolding'] * 1e9
    elif mode == 'VC':
        vinit = cmd['vcHolding']
        vc.amp1 = cmd['vcHolding']
        ic.amp = 0

    h.init()

    icRec.clear()
    vcRec.clear()

    h.finitialize(vinit)
    
    tstop = (dt*len(data)+2)
    h.continuerun(tstop)
    #neuron.run(t2)
    #t = t2

    #print len(out), out
    #out = np.array(out)[:len(data)]

    out = None
    if mode == 'IC':
        out = np.array(icRec)[:len(data)] * 1e-3  # + np.random.normal(size=len(data), scale=0.3e-3)
    elif mode == 'VC':
        out = np.array(vcRec)[:len(data)] * 1e-9  # + np.random.normal(size=len(data), scale=3.e-12)

    if len(out) != len(data):
        print("Warning: neuron sim output length mismatch: %d != %d" % (len(out), len(data)))
        out = np.pad(out, (0, len(data)-len(out)), 'constant', constant_values=(0, 0))
    
    return out[n_extra:]


# provide a visible test to make sure code is working and failures are not ours.
# call this from the command line to observe the clamp plot results
#
if __name__ == '__main__':
    import pyqtgraph as pg
    from acq4.util import Qt
    app = Qt.QApplication([])
    win = pg.GraphicsWindow()
    win.resize(1000,600)
    win.setWindowTitle('Testing hhSim.py')
    p = win.addPlot(title='VC')
    npts = 10000.
    x1 = 2000.
    x2 = 7000.
    x = np.arange(-100, 41, 10)
    cmd = np.ones((len(x), npts))*-65.0*1e-3
    data = np.zeros((len(x), npts))
    dt = 1e-4
    tb = np.arange(0, npts*dt, dt)
    for i, v in enumerate(x):
        print('V: ', v)
        cmd[i, x1:x2] = v*1e-3
        opts = {
            'mode': 'vc',
            'dt': dt,
            'data': cmd[i,:]
        }
        data[i,:] = run(opts)
        p.plot(tb, data[i])

    Qt.QApplication.instance().exec_()
    