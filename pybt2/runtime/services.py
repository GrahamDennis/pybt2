from typing import (
    Awaitable,
    Callable,
    Generic,
    Optional,
    TypeVar,
    cast,
)

from attr import frozen

from pybt2.runtime.captures import use_capture
from pybt2.runtime.fibre import CallContext
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.hooks import (
    AsyncResult,
    AsyncRunning,
    use_state,
    use_version,
)
from pybt2.runtime.types import CaptureKey, Dependencies, Key, Setter

ApiT = TypeVar("ApiT")
RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")

_ASYNC_RUNNING = AsyncRunning()


@frozen(weakref_slot=False)
class ApiCall(Generic[RequestT, ResponseT]):
    request: RequestT
    set_async_result: Setter[AsyncResult[ResponseT]]


@frozen(weakref_slot=False)
class UseApiCall(RuntimeCallableProps[AsyncResult[ResponseT]], Generic[ApiT, RequestT, ResponseT]):
    api: Callable[[ApiT, RequestT], Awaitable[ResponseT]]
    request: RequestT
    dependencies: Dependencies

    def __call__(self, ctx: CallContext) -> AsyncResult[ResponseT]:
        dependencies_version = use_version(ctx, dependencies=self.dependencies, key="version")
        async_result, set_async_result = use_state(
            ctx, cast(AsyncResult[ResponseT], _ASYNC_RUNNING), key=dependencies_version
        )

        use_capture(ctx, CaptureKey(self.api), ApiCall(self.request, set_async_result), key="capture")
        return async_result


def use_api_call(
    ctx: CallContext,
    api: Callable[[ApiT, RequestT], Awaitable[ResponseT]],
    request: RequestT,
    *,
    dependencies: Optional[Dependencies] = None,
    key: Optional[Key] = None,
) -> AsyncResult[ResponseT]:
    return ctx.evaluate_child(
        UseApiCall(api=api, request=request, dependencies=dependencies if dependencies is not None else [request]),
        key=key,
    )
