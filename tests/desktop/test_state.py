from datetime import datetime, timedelta, timezone
from threading import Event, get_ident
import time

from desktop.models import Login, User
from desktop.session import SessionState
from desktop.tasks import Tasks


def login(role='ADMIN'):
    return Login('x'*43, datetime.now(timezone.utc)+timedelta(hours=8), User(1,'example','Example',role))


def spin(tasks, predicate):
    end = time.monotonic()+3
    while not predicate() and time.monotonic() < end:
        tasks.drain()
        time.sleep(.005)
    assert predicate()


def test_session_roles_expiry_and_cleanup():
    s = SessionState()
    s.set(login())
    assert 'Employee Accounts' in s.destinations
    assert 'x'*43 not in repr(s)
    generation = s.generation
    s.clear()
    assert s.login is None and s.generation > generation
    s.set(login('AUDITOR'))
    assert 'Employee Accounts' not in s.destinations
    assert not s.expired()
    assert s.expired(datetime.now(timezone.utc)+timedelta(hours=9))


def test_main_thread_only_delivery_and_superseded_error():
    t = Tasks(workers=2)
    gate = Event()
    started = Event()
    seen = []
    main = get_ident()
    def old():
        started.set()
        gate.wait(2)
        raise ValueError('sensitive')
    t.submit('screen', old, lambda value,error: seen.append('old'))
    assert started.wait(1)
    t.submit('screen', lambda: 'new', lambda value,error: seen.append((value,get_ident())))
    spin(t, lambda: bool(seen))
    gate.set()
    t.close()
    assert seen == [('new', main)]


def test_abandoned_login_is_disposed_on_close():
    t = Tasks(workers=1)
    gate, started, disposed = Event(), Event(), Event()
    def work():
        started.set()
        gate.wait(2)
        return login()
    t.submit('login', work, lambda *_: (_ for _ in ()).throw(AssertionError('late UI')),
             lambda result: disposed.set())
    assert started.wait(1)
    before = time.monotonic()
    t.close()
    assert time.monotonic()-before < .1
    gate.set()
    assert disposed.wait(2)


def test_queued_result_disposed_when_invalidated():
    t = Tasks(workers=1)
    finished, disposed = Event(), Event()
    t.submit('login', lambda: finished.set() or login(), lambda *_: None, lambda _: disposed.set())
    assert finished.wait(1)
    t.invalidate()
    spin(t, disposed.is_set)
    t.close()


def test_backlog_is_bounded_and_shutdown_skips_queued_work():
    t = Tasks(workers=1, capacity=2)
    gate, started = Event(), Event()
    ran = []
    t.submit('one', lambda: started.set() or gate.wait(2), lambda *_: None)
    assert started.wait(1)
    assert t.submit('two', lambda: ran.append('two'), lambda *_: None)
    assert not t.submit('three', lambda: None, lambda *_: None)
    t.close()
    gate.set()
    time.sleep(.05)
    assert ran == []


def test_superseded_callbacks_are_released_without_navigation():
    t=Tasks(workers=1)
    gate,started=Event(),Event()
    t.submit('screen',lambda:started.set() or gate.wait(2),lambda *_:None)
    assert started.wait(1)
    seen=[]
    t.submit('screen',lambda:2,lambda *_:seen.append(2))
    gate.set()
    spin(t,lambda:bool(seen))
    assert t._callbacks=={}
    t.close()


def test_completed_worker_releases_request_captures():
    import gc
    import weakref
    class Secret:
        pass
    secret=Secret()
    reference=weakref.ref(secret)
    t=Tasks(workers=1)
    seen=[]
    t.submit('login',lambda captured=secret:True,lambda *_:seen.append(True))
    del secret
    spin(t,lambda:bool(seen))
    gc.collect()
    assert reference() is None
    t.close()


def test_rejected_replacement_still_invalidates_previous_query():
    t=Tasks(workers=1,capacity=1)
    gate,started=Event(),Event()
    seen=[]
    t.submit('screen',lambda:started.set() or gate.wait(2),lambda *_:seen.append('old query'))
    assert started.wait(1)
    assert not t.submit('screen',lambda:'new',lambda *_:seen.append('new query'))
    gate.set()
    time.sleep(.05)
    t.drain()
    assert seen==[]
    t.close()
