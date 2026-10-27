"""Keep cyclic Tk resource finalizers on the application's owning thread."""
import gc
from threading import get_ident
import time


class UiCollector:
    """One application lifetime; replace automatic cyclic GC with UI polling.

    Python may otherwise collect detached widget/font cycles during allocations
    on any HTTP worker. Tk font/image finalizers call Tcl and must stay on the UI
    thread. Reference counting remains enabled; workers never own Tk objects.
    """
    def __init__(self):
        self.owner=get_ident()
        self.restore_enabled=gc.isenabled()
        self.closed=False
        self.next_collection=time.monotonic()+2
        gc.disable()

    def poll(self):
        if get_ident()!=self.owner:
            raise RuntimeError('UI collection requires the owning thread')
        if not self.closed and time.monotonic()>=self.next_collection:
            gc.collect()
            self.next_collection=time.monotonic()+2

    def close(self):
        if get_ident()!=self.owner:
            raise RuntimeError('UI collection requires the owning thread')
        if not self.closed:
            gc.collect()
            self.closed=True
            if self.restore_enabled:
                gc.enable()
