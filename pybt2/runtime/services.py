from typing import (
    Awaitable,
    Callable,
    Generic,
    Optional,
    TypeVar,
    cast,
)

from attr import field, frozen

from pybt2.runtime.captures import use_capture
from pybt2.runtime.fibre import CallContext
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.hooks import (
    AsyncResult,
    AsyncRunning,
    use_state,
)
from pybt2.runtime.types import CaptureKey, Dependencies, Key, Setter

ApiT = TypeVar("ApiT")
RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")

_ASYNC_RUNNING = AsyncRunning()


def capture_request(request: RequestT) -> RequestT:
    return request


@frozen(weakref_slot=False)
class ApiCall(Generic[RequestT, ResponseT]):
    request: RequestT
    set_async_result: Setter[AsyncResult[ResponseT]]


@frozen(weakref_slot=False)
class UseApiCall(RuntimeCallableProps[AsyncResult[ResponseT]], Generic[ApiT, RequestT, ResponseT]):
    api: Callable[[ApiT, RequestT], Awaitable[ResponseT]]
    call: Callable[[Callable[[RequestT], Awaitable[ResponseT]]], Awaitable[ResponseT]] = field(eq=False)
    dependencies: Dependencies

    def __call__(self, ctx: CallContext) -> AsyncResult[ResponseT]:
        # FIXME: reset if dependencies change
        async_result, set_async_result = use_state(ctx, cast(AsyncResult[ResponseT], _ASYNC_RUNNING))

        request = self.call(cast(Callable[[RequestT], Awaitable[ResponseT]], capture_request))
        use_capture(ctx, CaptureKey(cast(str, self.api)), ApiCall(request, set_async_result))
        return async_result


def use_api_call(
    ctx: CallContext,
    *,
    api: Callable[[ApiT, RequestT], Awaitable[ResponseT]],
    call: Callable[[Callable[[RequestT], Awaitable[ResponseT]]], Awaitable[ResponseT]],
    dependencies: Dependencies,
    key: Optional[Key] = None,
) -> AsyncResult[ResponseT]:
    return ctx.evaluate_child(UseApiCall(api, call, dependencies), key=key)
