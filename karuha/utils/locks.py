"""
Synchronization primitives.

Reimplement asyncio.Lock for Python 3.12 compatibility.
"""

import asyncio
import sys


if sys.version_info >= (3, 12):
    from asyncio.locks import Lock
else:
    import collections
    import threading
    from abc import ABC
    from asyncio.locks import Lock as _Lock

    _global_lock = threading.Lock()

    class Lock(ABC):
        """Primitive lock objects.

        A primitive lock is a synchronization primitive that is not owned
        by a particular coroutine when locked.  A primitive lock is in one
        of two states, 'locked' or 'unlocked'.

        It is created in the unlocked state.  It has two basic methods,
        acquire() and release().  When the state is unlocked, acquire()
        changes the state to locked and returns immediately.  When the
        state is locked, acquire() blocks until a call to release() in
        another coroutine changes it to unlocked, then the acquire() call
        resets it to locked and returns.  The release() method should only
        be called in the locked state; it changes the state to unlocked
        and returns immediately.  If an attempt is made to release an
        unlocked lock, a RuntimeError will be raised.

        When more than one coroutine is blocked in acquire() waiting for
        the state to turn to unlocked, only one coroutine proceeds when a
        release() call resets the state to unlocked; first coroutine which
        is blocked in acquire() is being processed.

        acquire() is a coroutine and should be called with 'await'.

        Locks also support the asynchronous context management protocol.
        'async with lock' statement should be used.

        Usage:

            lock = Lock()
            ...
            await lock.acquire()
            try:
                ...
            finally:
                lock.release()

        Context manager usage:

            lock = Lock()
            ...
            async with lock:
                ...

        Lock objects can be tested for locking state:

            if not lock.locked():
            await lock.acquire()
            else:
            # lock is acquired
            ...
        """

        _loop = None

        def __init__(self):
            self._waiters = None
            self._locked = False

        def __repr__(self):
            res = super().__repr__()
            extra = "locked" if self._locked else "unlocked"
            if self._waiters:
                extra = f"{extra}, waiters:{len(self._waiters)}"
            return f"<{res[1:-1]} [{extra}]>"

        def locked(self):
            """Return True if lock is acquired."""
            return self._locked

        async def acquire(self):
            """Acquire a lock.

            This method blocks until the lock is unlocked, then sets it to
            locked and returns True.
            """
            if not self._locked and (self._waiters is None or all(w.cancelled() for w in self._waiters)):
                self._locked = True
                return True

            if self._waiters is None:
                self._waiters = collections.deque()
            fut = self._get_loop().create_future()
            self._waiters.append(fut)

            # Finally block should be called before the CancelledError
            # handling as we don't want CancelledError to call
            # _wake_up_first() and attempt to wake up itself.
            try:
                try:
                    await fut
                finally:
                    self._waiters.remove(fut)
            except asyncio.CancelledError:
                if not self._locked:
                    self._wake_up_first()
                raise

            self._locked = True
            return True

        def release(self):
            """Release a lock.

            When the lock is locked, reset it to unlocked, and return.
            If any other coroutines are blocked waiting for the lock to become
            unlocked, allow exactly one of them to proceed.

            When invoked on an unlocked lock, a RuntimeError is raised.

            There is no return value.
            """
            if self._locked:
                self._locked = False
                self._wake_up_first()
            else:
                raise RuntimeError("Lock is not acquired.")

        def _wake_up_first(self):
            """Wake up the first waiter if it isn't done."""
            if not self._waiters:
                return
            try:
                fut = next(iter(self._waiters))
            except StopIteration:
                return

            # .done() necessarily means that a waiter will wake up later on and
            # either take the lock, or, if it was cancelled and lock wasn't
            # taken already, will hit this again and wake up a new waiter.
            if not fut.done():
                fut.set_result(True)

        def _get_loop(self):
            loop = asyncio.get_running_loop()

            if self._loop is None:
                with _global_lock:
                    if self._loop is None:
                        self._loop = loop
            if loop is not self._loop:
                raise RuntimeError(f"{self!r} is bound to a different event loop")
            return loop

        async def __aenter__(self):
            await self.acquire()
            # We have no use for the "as ..."  clause in the with
            # statement for locks.
            return None

        async def __aexit__(self, exc_type, exc, tb):
            self.release()

    Lock.register(_Lock)
