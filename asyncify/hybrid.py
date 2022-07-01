from __future__ import annotations

import functools
import inspect
import re
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Generic, Optional, TypeVar, Union

if TYPE_CHECKING:
    from types import FrameType
    from typing_extensions import Self


__all__ = ('HybridFunction', 'hybrid_function')


T_sync = TypeVar('T_sync')
T_async = TypeVar('T_async')


class HybridFunction(Generic[T_sync, T_async]):
    regex = re.compile(r'await\s+(\w|\.)*\(.*\)')

    def __init__(
        self, name: str, sync_callback: Callable[..., T_sync], async_callback: Callable[..., Coroutine[Any, Any, T_async]]
    ):
        self._name = name
        if len(inspect.signature(sync_callback).parameters) != len(inspect.signature(async_callback).parameters):
            raise TypeError('Both function signatures must be the same.')

        self.sync_callback = sync_callback
        self.async_callback = async_callback
        functools.update_wrapper(self, self.sync_callback)
        self._instance: Optional[object] = None

    def __get__(self, instance: object, owner: type) -> Self:
        new_self = self.__class__(self._name, self.sync_callback, self.async_callback)
        new_self._instance = instance
        return new_self

    def _check_regex(self, code_context: str) -> bool:
        search = self.regex.search(code_context)
        if not search:
            return False

        span = search.span()
        if self._name not in code_context[span[0]:span[1]]:
            return False

        return True

    def _get_frame(self, current_frame: FrameType) -> str:
        for frame in inspect.getouterframes(current_frame):
            if not frame.code_context:
                continue

            if self._name in frame.code_context[0]:
                return frame.code_context[0]
        raise RuntimeError('Could not tell if it should call sync or async.')

    def __call__(self, *args: Any, **kwargs: Any) -> Union[T_sync, Coroutine[Any, Any, T_async]]:
        if self._instance:
            args = (self._instance, *args)

        frame = inspect.currentframe()
        assert frame is not None

        code_context = self._get_frame(frame).strip()
        if self._check_regex(code_context):
            return self.async_callback(*args, **kwargs)
        return self.sync_callback(*args, **kwargs)


def hybrid_function(
    name: str, sync_callback: Callable[..., T_sync], async_callback: Callable[..., Coroutine[Any, Any, T_async]]
) -> HybridFunction[T_sync, T_async]:
    """
    Do multiple things depending on whether it was awaited or not!


    Parameters
    ----------
    name: :class:`str`
        The name of the new function. This must be the same as the function name to work.
    sync_callback: ``Callable[..., Any]``
        The callable to call if it is not awaited.
    async_callback: ``Callable[..., Coroutine]``
        The callable to call if it is awaited.


    Example
    --------
    .. code:: py

        import asyncify
        import discord  # discord.py example

        class Client(discord.Client):
            get_or_fetch_user = asyncify.hybrid_function(
                                'get_or_fetch_user',
                                 discord.Client.get_user,
                                 discord.Client.fetch_user
            )

        client = Client()

        client.get_or_fetch_user(739510612652195850)  # sync cache lookup
        await client.get_or_fetch_user(739510612652195850)  # async api call


    .. warning::
        Make the to name the function uniquely. Functions with the same name could be called unexpectedly.
    """
    return HybridFunction[T_sync, T_async](name, sync_callback, async_callback)
