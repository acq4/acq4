import time
from acq4.util.prioritylock import PriorityLock
import acq4


def test_prioritylock():
    l = PriorityLock()
    with l.acquire(name="f1") as f1:             # test context manager
        f1.wait(timeout=1)
        f2 = l.acquire(name="f2")                # lock when ready
        f3 = l.acquire(100, name="f3")           # higher priority
        f4 = l.acquire(10, name="f4")            # mid priority
        f5 = l.acquire(10, name="f5")            # same priority, but later in queue
        with l.acquire(1000, name="f6") as f6:   # release before acquire possible
            pass
        f7 = l.acquire(1000, name="f7")          # release before acquire possible
        f7.release()
        time.sleep(0.01)
        
        assert all([f1.acquired, not f2.acquired, not f3.acquired, not f4.acquired, not f5.acquired, not f6.acquired, not f7.acquired])
    
    f3.wait()
    assert all([not f1.acquired, not f2.acquired, f3.acquired, not f4.acquired, not f5.acquired, not f6.acquired, not f7.acquired])
    f3.release()
    f4.wait()
    assert all([not f1.acquired, not f2.acquired, not f3.acquired, f4.acquired, not f5.acquired, not f6.acquired, not f7.acquired])
    f4.release()
    f5.wait()
    assert all([not f1.acquired, not f2.acquired, not f3.acquired, not f4.acquired, f5.acquired, not f6.acquired, not f7.acquired])
    f5.release()
    f2.wait()
    assert all([not f1.acquired, f2.acquired, not f3.acquired, not f4.acquired, not f5.acquired, not f6.acquired, not f7.acquired])
    f2.release()
    time.sleep(0.01)
    assert all([not f1.acquired, not f2.acquired, not f3.acquired, not f4.acquired, not f5.acquired, not f6.acquired, not f7.acquired])
    
    
    
if __name__ == '__main__':
    test_prioritylock()
