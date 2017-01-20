import re


class MultiPatchLog(object):
    def __init__(self, filename=None):
        self._devices = {}
        self._minTime = None
        self._maxTime = None
        
        if filename is not None:
            self.read(filename)

    def read(self, file):
        for line in open(file, 'r').readlines():
            # parse line
            fields = re.split(r',\s*', line.strip())
            time, eventType, device = [eval(v) for v in fields[:3]]
            data = fields[3:]
            time = float(time)
            if self._minTime is None:
                self._minTime = time
                self._maxTime = time
            else:
                self._minTime = min(self._minTime, time)
                self._maxTime = max(self._maxTime, time)

            event = {
                'event_time': time,
                'device': device,
                'event': eventType,
            }
            if eventType == 'move_stop':
                event['position'] = list(map(float, data))

            # initialize irregular time series if needed
            if device not in self._devices:
                self._devices[device] = {
                    'position': IrregularTimeSeries(interpolate=True)
                }
            
            # Record event into irregular time series
            dev = self._devices[device]
            time = event['event_time']
            if event['event'] == 'move_start':
                posSeries = dev['position']
                lastPos = posSeries.lastValue()
                if lastPos is not None:
                    posSeries[time] = lastPos
            elif event['event'] == 'move_stop':
                dev['position'][time] = event['position']

    def devices(self):
        return list(self._devices.keys())

    def state(self, time):
        state = {}
        for dev in self.devices():
            state[dev] = {'position': self._devices[dev]['position'][time]}
        return state
        


class IrregularTimeSeries(object):
    """An irregularly-sampled time series.
    
    Allows efficient retrieval of the series value at any time using a lookup table.
    Intended for cases where the lookup table would be reasonably-sized (for example,
    an hour of events indexed at 1-second resolution). For larger data sets, a 
    b-tree would be a more reasonable approach.
    
    If enabled, values are interpolated linearly. Values may be of any type,
    but only scalar, array, and tuple-of-scalar types may be interpolated.
    """
    def __init__(self, data=None, interpolate=False, resolution=1.0):
        self.interpolate = interpolate
        self._resolution = resolution
        
        self.events = []
        self.index = []  # each value maps a time in seconds to the index of the value recorded immediately after the time
        self._startTime = None
        
        if data is not None:
            self.extend(data)
    
    def __setitem__(self, time, value):
        if len(self.events) > 0 and time <= self.events[-1][0]:
            raise ValueError("Time points must be added in increasing order.")
        
        if self._startTime is None:
            self._startTime = time
        i = self._getIndex(time)

        # Extend index
        dif = i + 1 - len(self.index)
        if dif > 0:
            self.index.extend([len(self.events)] * dif)
        self.index[i] = len(self.events)
        
        self.events.append((float(time), value))
       
    def extend(self, data):
        for t,v in data:
            self[t] = v
       
    def __getitem__(self, time):
        events = self.events
        if len(events) == 0:
            return None
        if time <= self._startTime:
            return None
        if time >= events[-1][0]:
            return events[-1][1]
        
        # Use index to find a nearby event
        i = self.index[min(self._getIndex(time), len(self.index)-1)]
        
        if events[i][0] > time:
            # walk backward to the requested event
            while self.events[i][0] > time:
                i -= 1
        elif events[i][0] < time:
            # walk forward to the requested event
            while i+1 < len(self.events) and self.events[i+1][0] <= time:
                i += 1
        else:
            return events[i][1]
        
        # interpolate if requested
        if self.interpolate:
            t1, v1 = events[i]
            t2, v2 = events[i+1]
            return self._interpolate(time, v1, v2, t1, t2)
        else:
            return events[i][1]

    def _getIndex(self, t):
        return int((t - self._startTime) / self._resolution)

    def _interpolate(self, t, v1, v2, t1, t2):
        s = (t - t1) / (t2 - t1)
        assert s >= 0.0 and s <= 1.0
        if isinstance(v1, (tuple, list)):
            return tuple([v1[k] * (1.0 - s) + v2[k] * s for k in range(len(v1))])
        else:
            return v1 * (1.0 - s) + v2 * s
    
    def firstValue(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[0][1]

    def lastValue(self):
        if len(self.events) == 0:
            return None
        else:
            return self.events[-1][1]

    def __len__(self):
        return len(self.events)
