import asyncio
from typing import Awaitable, MutableSequence


class DynamicGatheringFuture(asyncio.Future):
    """
    A dynamic version of `asyncio.tasks._GatheringFuture`.

    It allows to add new tasks to the gathering future.
    """

    __slots__ = ["children", "nfinished", "_cancel_requested"]

    def __init__(self, children: MutableSequence[asyncio.Future], *, loop=None):
        super().__init__(loop=loop)
        self.children = children
        self.nfinished = 0
        self._cancel_requested = False
        done_futs = []

        for child in children:
            if child.done():
                done_futs.append(child)
            else:
                child.add_done_callback(self._done_callback)
        
        for child in done_futs:
            self._done_callback(child)

    def add_task(self, fut: asyncio.Future) -> None:
        if self.done():  # pragma: no cover
            raise RuntimeError("cannot add child to cancelled parent")
        fut.add_done_callback(self._done_callback)
        self.children.append(fut)

    def add_coroutine(self, coro: Awaitable) -> None:
        fut = asyncio.ensure_future(coro)
        if fut is not coro:
            # 'coro' was not a Future, therefore, 'fut' is a new
            # Future created specifically for 'coro'.  Since the caller
            # can't control it, disable the "destroy pending task"
            # warning.
            fut._log_destroy_pending = False  # type: ignore[attr-defined]
        self.add_task(fut)
    
    def cancel(self, msg=None) -> bool:  # pragma: no cover
        if self.done():
            return False
        ret = False
        for child in self.children:
            cancelled = child.cancel(msg=msg) if msg is not None else child.cancel()  # type: ignore
            if cancelled:
                ret = True
        if ret:
            # If any child tasks were actually cancelled, we should
            # propagate the cancellation request regardless of
            # *return_exceptions* argument.  See issue 32684.
            self._cancel_requested = True
        return ret

    def _done_callback(self, fut: asyncio.Future) -> None:
        self.nfinished += 1

        if self.done():  # pragma: no cover
            if not fut.cancelled():
                # Mark exception retrieved.
                fut.exception()
            return

        if fut.cancelled():
            # Check if 'fut' is cancelled first, as
            # 'fut.exception()' will *raise* a CancelledError
            # instead of returning it.
            try:
                exc = fut._make_cancelled_error()  # type: ignore
            except AttributeError:
                exc = asyncio.CancelledError()
            self.set_exception(exc)
            return
        else:
            exc = fut.exception()
            if exc is not None:  # pragma: no cover
                self.set_exception(exc)
                return

        if self.nfinished == len(self.children):
            # All futures are done; create a list of results
            # and set it to the 'outer' future.
            results = []

            for fut in self.children:
                if fut.cancelled():  # pragma: no cover
                    # Check if 'fut' is cancelled first, as
                    # 'fut.exception()' will *raise* a CancelledError
                    # instead of returning it.
                    res = asyncio.CancelledError(
                        getattr(fut, "_cancel_message", '') or ''
                    )
                else:
                    res = fut.exception()
                    if res is None:
                        res = fut.result()
                results.append(res)

            if self._cancel_requested:  # pragma: no cover
                # If gather is being cancelled we must propagate the
                # cancellation regardless of *return_exceptions* argument.
                # See issue 32684.
                try:
                    exc = fut._make_cancelled_error()  # type: ignore
                except AttributeError:
                    exc = asyncio.CancelledError()
                self.set_exception(exc)
            else:
                self.set_result(results)
