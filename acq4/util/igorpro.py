import queue
import sys
import threading
import pywintypes
import numpy as np
import subprocess
import concurrent.futures
import atexit
import json
import zmq
import logging

from acq4.util.json_encoder import IgorJSONEncoder
from acq4.util import Qt


logger = logging.getLogger('igorpro')

dtypes = { 
    0x02: 'float32',
    0x04: 'float64',
    0x08: 'byte',
    0x10: 'short',
    0x20: 'long',
    0x48: 'ubyte',
    0x50: 'ushort',
    0x60: 'ulong',
    0x01: 'complex',
    0x00: 'str',
}

float_types = {
    "NT_FP32": np.float32,
    "NT_FP64": np.float64
}



class IgorCallError(Exception):
    FAILED = 1
    TIMEDOUT = 2
    def __init__(self, message, errno=1):
        self.errno = errno
        super(IgorCallError, self).__init__(message)


zmq_context = zmq.Context()
def close_context():
    zmq_context.term()
atexit.register(close_context)


class IgorBridge(Qt.QObject):
    sigTestPulseReady = Qt.Signal(object, object)  # message, data_buffer
    sigMiesConfigurationFinished = Qt.Signal()
    sigMiesTestPulseStateChanged = Qt.Signal(bool)
    sigMiesClampModeChanged = Qt.Signal(int, str)  # headstage, mode
    sigMiesClampStateChanged = Qt.Signal(int, object)  # headstage, state

    def __init__(self, req_port=5670, sub_port=5770):
        super().__init__()

        self.topic_filters = {
            "now": b"testpulse:results live", 
            "live": b"testpulse:results live with data",
            "1s": b"testpulse:results 1s update", 
            "5s": b"testpulse:results 5s update", 
            "10s": b"testpulse:results 10s update",
            "HB": b"heartbeat", #empty bytearray
            "DA_CHANGE": b"data acquisition:state change",
            "CONFIG_FIN": b"configuration:finished",
            "AMP_CHANGE": b"amplifier:set value",
            "AMP_CLAMP_MODE_CHANGE": b"amplifier:clamp mode"
            }
        
        self.clamp_mode_mapping = {
            "V_CLAMP_MODE": "VC",
            "I_CLAMP_MODE": "IC",
            "I_EQUAL_ZERO_MODE": "I=0"
        }
        
        self.req_thread = IgorReqThread(address=f"tcp://localhost:{req_port}")
        self.sub_socket_port = sub_port
        self.run_sub_socket = True
        self.sub_socket_thread = threading.Thread(target=self.sub_socket_run, daemon=True)
        self.sub_socket_thread.start()
        atexit.register(self.quit)

    def sub_socket_run(self):
        sub_socket = zmq_context.socket(zmq.SUB)
        sub_socket.setsockopt(zmq.LINGER, 500)
        sub_socket.setsockopt(zmq.IDENTITY, b"miesmonitor_sub")
        sub_socket.setsockopt(zmq.RCVTIMEO, 500) # up from zero
        sub_socket.setsockopt(zmq.SUBSCRIBE, self.topic_filters["live"])
        sub_socket.setsockopt(zmq.SUBSCRIBE, self.topic_filters["DA_CHANGE"])
        sub_socket.setsockopt(zmq.SUBSCRIBE, self.topic_filters["CONFIG_FIN"])
        sub_socket.setsockopt(zmq.SUBSCRIBE, self.topic_filters["AMP_CHANGE"])
        sub_socket.setsockopt(zmq.SUBSCRIBE, self.topic_filters["AMP_CLAMP_MODE_CHANGE"])
        sub_socket.connect(f"tcp://localhost:{self.sub_socket_port}")

        while self.run_sub_socket:
            try:
                pub_response = sub_socket.recv_multipart()
                topic = pub_response[0]
                message = json.loads(pub_response[1].decode("utf-8"))
                # if topic != self.topic_filters["live"]:
                #     print("IGOR PUB:", topic, message)

                if topic == self.topic_filters["DA_CHANGE"]:
                    val = message["tp"] == "starting"
                    self.sigMiesTestPulseStateChanged.emit(val)
                elif topic == self.topic_filters["live"]:
                    self.sigTestPulseReady.emit(message, pub_response[2])
                elif topic == self.topic_filters["CONFIG_FIN"]:
                    self.sigMiesConfigurationFinished.emit()
                elif topic == self.topic_filters["AMP_CLAMP_MODE_CHANGE"]:
                    clamp_mode = self.clamp_mode_mapping[message['clamp mode']['new']]
                    headstage = int(message['headstage'])
                    self.sigMiesClampModeChanged.emit(headstage, clamp_mode)
                elif topic == self.topic_filters["AMP_CHANGE"]:
                    self.sigMiesClampStateChanged.emit(int(message['headstage']), message['amplifier action'])
            except zmq.error.Again:
                pass
            except zmq.error.ZMQError as e:
                # Operation cannot be accomplished in current state
                pass

    def tryReconnect(func):
        def _tryReconnect(self, *args, **kwds):
            if self.app is None:
                self.connect()
            try:
                return func(self, *args, **kwds)
            except pywintypes.com_error as exc:
                if exc.args[0] == -2147023174:
                    # server unavailable; try reconnecting
                    self.connect()
                    return func(self, *args, **kwds)
                else:
                    raise
        return _tryReconnect

    @staticmethod
    def igorProcessExists():
        """Return True if an Igor process is currently running.
        """
        return 'Igor.exe' in subprocess.check_output(['wmic', 'process', 'get', 'description,executablepath'])        

    def __call__(self, cmd, *args):
        logger.debug("Igor request: %s %s", cmd, args)
        return self.req_thread.send(cmd, *args)
    
    def quit(self):
        self.run_sub_socket = False
        self.req_thread.stop()


class IgorReqThread(threading.Thread):
    def __init__(self, address):
        self.address = address
        self.stop_flag = False
        self.send_queue = queue.Queue()
        self.unresolved_futures = {}
        self.resolved_ids = set()
        self.next_result_id = 0
        self.running = True
        super().__init__(target=self._req_loop, daemon=True, name="IgorReqThread")
        self.start()
        atexit.register(self.stop)

    def send(self, cmd, *args):
        if not self.running:
            raise Exception("IGOR thread is already shut down; cannot send request.")
        fut = concurrent.futures.Future()
        self.send_queue.put((cmd, args, fut))
        return fut

    def stop(self):
        self.stop_flag = True

    def _req_loop(self):
        try:
            self.socket = zmq_context.socket(zmq.DEALER)
            self.socket.setsockopt(zmq.IDENTITY, b"igorbridge")
            self.socket.setsockopt(zmq.SNDTIMEO, 1000)
            self.socket.setsockopt(zmq.RCVTIMEO, 100)
            success = self.socket.connect(self.address)

            while not self.stop_flag:
                self._check_send()
                self._check_recv()
        finally:
            self.running = False

            # resolve all remaining futures and unhandled requests
            for f in self.unresolved_futures.values():
                f.set_exception(RuntimeError("IGOR thread closed before getting result from this request"))
            while self.send_queue.qsize() > 0:
                cmd, params, fut = self.send_queue.get(block=False)
                fut.set_exception(RuntimeError("IGOR thread closed before getting result from this request"))

            self.socket.close()

    def _check_send(self):
        # Send some (but not all) messages waiting in the queue
        for i in range(10):
            if not zmq_context.closed:
                try:
                    cmd, params, fut = self.send_queue.get(block=False)
                except queue.Empty:
                    break
                try:
                    msg_id = self.next_result_id
                    self.next_result_id += 1
                    self.unresolved_futures[msg_id] = fut
                    # print(f"IGOR SEND: {msg_id} {cmd} {params}")
                    self.socket.send_multipart(self.format_call(cmd, params, msg_id))
                except zmq.error.Again:
                    pass
                except zmq.error.ContextTerminated:
                    pass

    def _check_recv(self):
        if not zmq_context.closed:
            try:
                parts = self.socket.recv_multipart()
                reply = json.loads(parts[1])
                try:
                    message_id = int(reply["messageID"])
                except KeyError as ke:
                    raise RuntimeError(f"Igor message has no ID: {reply}")
                # print(f"IGOR RECV: {message_id} {reply}")
                try:
                    future = self.unresolved_futures.pop(message_id)
                except KeyError:
                    if message_id in self.resolved_ids:
                        raise ValueError(f"Received IGOR message {message_id} multiple times.")
                    else:
                        raise ValueError(f"Received unexpectd IGOR message {message_id}")
                self.resolved_ids.add(message_id)

                if future is None:
                    raise RuntimeError(f"No future found for messageID {message_id}")
                try:
                    reply = self.parse_reply(reply)
                    future.set_result(reply)
                except IgorCallError as e:
                    future.set_exception(e)
            except zmq.error.Again:
                pass
            except zmq.error.ContextTerminated:
                pass
            except zmq.error.ZMQError:
                pass

    def format_call(self, cmd, params, message_id):
        call = {"version": 1,
                "messageID": str(message_id),
                "CallFunction": {
                    "name": cmd,
                    "params": params}
                }
        msg = [b"", json.dumps(call, cls=IgorJSONEncoder).encode()]
        # print("send to igor:", msg)
        return msg

    def parse_reply(self, reply):
        # print("received from igor:", reply)
        err = reply.get("errorCode", {}).get("value", None)
        if err is None:
            raise RuntimeError("Invalid response from Igor")
        elif err != 0:
            msg = reply.get("errorCode", {}).get("msg", "")
            raise IgorCallError("Call failed with message: {}".format(msg))

        result = reply.get("result", {})
        if isinstance(result, list):
            return tuple([self._parse_return_value(r) for r in result])
        else:
            return self._parse_return_value(result)
            
    def _parse_return_value(self, result):
            restype = result.get("type", "")
            val = result.get("value", None)
            if (restype == "wave") and (val is not None):
                return self.parse_wave(val)
            else:
                return val

    def parse_wave(self, jsonWave):
        dtype = float_types.get(jsonWave["type"], float)
        shape = jsonWave["dimension"]["size"]
        raw = np.array(jsonWave["data"]["raw"], dtype=dtype)
        return raw.reshape(shape, order="F")
    

class IgorSubThread:
    def __init__(self, address):
        self.address = address
        self.stop_flag = False

    def stop(self):
        self.stop_flag = True




if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        path = 'root:MIES:ITCDevices:ITC1600:Device0'
        file = 'OscilloscopeData'
    else:
        path, file = sys.argv[1:3]

    import pyqtgraph as pg
    app = pg.mkQApp()
    plt = pg.plot(labels={'bottom': ('Time', 's')})
    igor = IgorThread()
    fut = []

    def update():
        global data, scaling, fut
        if not plt.isVisible():
            timer.stop()
            return

        if len(fut) < 10:
            fut.append(igor.getWave(path, file))

        if fut[0].done():
            data, scaling = fut.pop(0).result()
            #data, scaling = igor.getWave('root:MIES:ITCDevices:ITC1600:Device0:TestPulse', 'TestPulseITC')
            x = np.arange(data.shape[0]) * (scaling[0][0] * 1e-3)
            plt.clear()
            if data.ndim == 2:
                plt.plot(x, data[:,-1])
            else:
                plt.plot(x, data)


    timer = Qt.QTimer()
    timer.timeout.connect(update)
    timer.start(10)

    app.exec_()