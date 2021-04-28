from __future__ import print_function, division

import weakref
from threading import Lock, Thread, Event

from six.moves import queue

from .future import Future


class PriorityLock(object):
    """Mutex with asynchronous locking and priority queueing.
    
    The purpose of this class is to provide a mutex that:
    - Uses futures for acquiring locks asynchronously
    - Allows locks to be acquired in priority order
    
    
    Examples::
       
        lock = PriorityLock()
        
        # manual lock / wait / release
        req = lock.acquire()
        req.wait()  # wait for lock to be acquired
        # .. do stuff while lock is acquired
        req.release()
        
        # context manager
        with lock.acquire() as req:
            req.wait()
            # .. do stuff while lock is acquired
        
    """

    def __init__(self, name=None):
        self.name = name
        self.req_count = Counter()
        self.lock_queue = queue.PriorityQueue()

        self.unlock_event = Event()
        self.unlock_event.set()

        self.lock_thread = Thread(target=self._lock_loop)
        self.lock_thread.daemon = True
        self.lock_thread.start()

    def acquire(self, priority=0, name=None):
        """Return a Future that completes when the lock is acquired.
        
        Higher priority values will be locked first.
        """
        fut = PriorityLockRequest(self, name=name)
        # print("request lock:", fut)
        self.lock_queue.put((-priority, next(self.req_count), fut))
        return fut

    def _release_lock(self, fut):
        with fut._acq_lock:
            # print("release request:", fut)
            if fut.released:
                return
            fut._released = True
            if fut.acquired:
                # print("release lock:", fut)
                fut._acquired = False
                self.unlock_event.set()
            else:
                fut._taskDone(interrupted=True)

    def _lock_loop(self):
        while True:
            # wait for lock to become available
            self.unlock_event.wait()

            # get next lock request
            while True:
                _, _, fut = self.lock_queue.get()
                with fut._acq_lock:
                    if fut._released:
                        # future has already been released; don't assign lock
                        continue
                    # assign lock to this request
                    # print("assign lock:", fut)
                    fut._acquired = True
                    fut._taskDone()
                    self.unlock_event.clear()
                    break

    def __repr__(self):
        return "<%s %s 0x%x>" % (self.__class__.__name__, self.name, id(self))


class PriorityLockRequest(Future):
    def __init__(self, mutex, name):
        Future.__init__(self)
        self.mutex = weakref.ref(mutex)
        self.name = name
        self._acq_lock = Lock()
        self._wait_event = Event()
        self._acquired = False
        self._released = False

    @property
    def acquired(self):
        """If True, then this request currently has the lock acquired and prevents other requests
        from acquiring the lock.
        """
        return self._acquired

    @property
    def released(self):
        """If True, then this request has released its lock (if any) and can never acquire the lock again.
        """
        return self._released

    def _wait(self, timeout):
        self._wait_event.wait(timeout=timeout)

    def percentDone(self):
        return 100 if (self.acquired or self.released) else 0

    def release(self):
        """Release this lock request.
        
        If the lock is currently acquired, then it is released and another queued request may
        acquire the lock in turn. If the lock is not already acquired, then this request is simply 
        cancelled and will never acquire a lock.
        """
        mutex = self.mutex()
        if mutex is None:
            return
        mutex._release_lock(self)

    def _taskDone(self, *args, **kwds):
        self._wait_event.set()
        Future._taskDone(self, *args, **kwds)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()

    def __repr__(self):
        return "<%s %s 0x%x>" % (self.__class__.__name__, self.name, id(self))


class Counter(object):
    """Just a thread-safe counter, returns the next integer every time next() is called.
    """

    def __init__(self):
        self.value = 0
        self.lock = Lock()

    def __iter__(self):
        return self

    def __next__(self):  # for py3
        with self.lock:
            self.value += 1
            return self.value - 1

    def next(self):  # for py2
        return self.__next__()
