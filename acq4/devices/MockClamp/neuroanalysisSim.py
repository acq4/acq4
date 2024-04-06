from neuroanalysis.data import TSeries
from neuroanalysis.neuronsim.model_cell import ModelCell

model_cell = ModelCell()
model_cell.enable_mechs(['leak', 'lgkfast', 'lgkslow', 'lgkna'])

model_cell.clamp.ra = 10e6
model_cell.clamp.cpip = 3e-12
model_cell.soma.cap = 100e-12


def run(cmd: dict):
    """
    Accept command like::
        {
            'dt': 1e-4,
            'mode': 'ic',
            'data': np.array([...]),
        }

    Return array of Vm or Im values.
    """
    global model_cell
    mode = cmd['mode'].lower()
    cmd_ts = TSeries(cmd['data'], dt=cmd['dt'])
    result = model_cell.test(cmd_ts, mode)
    return result['primary'].data
