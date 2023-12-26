import asyncio
from typing import Awaitable, Callable, Generic, Iterator, Optional, ParamSpec, Tuple, TypeVar, cast

from attr import field, frozen
from typing_extensions import Self, override

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import (
    NO_PREDECESSORS,
    Dependencies,
    FibreNodeFunction,
    FibreNodeState,
    Key,
    OnDispose,
    Reducer,
    Setter,
    Task,
)

T = TypeVar("T")

UseStateResult = Tuple[T, Setter[T]]


@frozen
class UseStateHook(FibreNodeFunction[UseStateResult[T], None, Reducer[T]], Generic[T]):
    value: T = field(eq=False)

    @override
    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, UseStateResult[T], None, Reducer[T]],
        previous_state: Optional[FibreNodeState[Self, UseStateResult[T], None]],
        enqueued_updates: Iterator[Reducer[T]],
    ) -> FibreNodeState[Self, UseStateResult[T], None]:
        value: T
        setter: Setter[T]
        result_version: int

        if previous_state is not None:
            previous_value, previous_setter = previous_state.result
            value = previous_value
            setter = previous_setter
            for update in enqueued_updates:
                value = cast(Callable[[T], T], update)(value) if callable(update) else cast(T, update)
            if value == previous_value:
                return previous_state
            result_version = previous_state.result_version + 1
        else:
            value = self.value

            def setter(reducer: Reducer[T]) -> None:
                fibre_node.enqueue_update(reducer, fibre)

            result_version = 1
        return FibreNodeState(
            props=self,
            result=(value, setter),
            result_version=result_version,
            state=None,
            predecessors=NO_PREDECESSORS,
        )


def use_state(ctx: CallContext, value: T, key: Optional[Key] = None) -> Tuple[T, Setter[T]]:
    return ctx.evaluate_child(UseStateHook(value), key=key)


UseResourceHookResourceFactory = Callable[[OnDispose], T]
UseResourceHookState = Optional[Task]


@frozen
class UseResourceHook(FibreNodeFunction[T, UseResourceHookState, None], Generic[T]):
    resource_factory: UseResourceHookResourceFactory[T] = field(eq=False)
    dependencies: Dependencies

    @override
    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, T, UseResourceHookState, None],
        previous_state: Optional[FibreNodeState[Self, T, UseResourceHookState]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, T, UseResourceHookState]:
        if previous_state is not None and previous_state.props.dependencies == self.dependencies:
            return previous_state
        if previous_state is not None and previous_state.state is not None:
            previous_state.state()

        result, dispose = self.construct_resource(self.resource_factory)
        result_version: int
        if previous_state is None:
            result_version = 1
        else:
            previous_result_version = previous_state.result_version
            result_version = previous_result_version if result == previous_state.result else previous_result_version + 1

        return FibreNodeState(
            props=self,
            result=result,
            result_version=result_version,
            state=dispose,
            predecessors=NO_PREDECESSORS,
        )

    def construct_resource(self, resource_factory: UseResourceHookResourceFactory[T]) -> tuple[T, Optional[Task]]:
        dispose_tasks: list[Task] = []

        def on_dispose(task: Task) -> None:
            dispose_tasks.append(task)

        value = resource_factory(on_dispose)

        if not dispose_tasks:
            return value, None

        def cleanup() -> None:
            for dispose_task in dispose_tasks:
                dispose_task()

        return value, cleanup

    @classmethod
    def dispose(cls, state: FibreNodeState[Self, T, UseResourceHookState]) -> None:
        if state.state is not None:
            state.state()


def use_resource(
    ctx: CallContext,
    resource_factory: UseResourceHookResourceFactory[T],
    dependencies: Dependencies,
    key: Optional[Key] = None,
) -> T:
    return ctx.evaluate_child(
        UseResourceHook(resource_factory, dependencies),
        key=key,
    )


def use_memo(ctx: CallContext, factory: Callable[[], T], dependencies: Dependencies, key: Optional[Key] = None) -> T:
    return use_resource(ctx, lambda _: factory(), dependencies, key)


P = ParamSpec("P")


def use_callback(
    ctx: CallContext, callback: Callable[P, T], dependencies: Dependencies, key: Optional[Key] = None
) -> Callable[P, T]:
    return use_resource(ctx, lambda _: callback, dependencies, key)


def use_effect(
    ctx: CallContext, effect: Callable[[OnDispose], None], dependencies: Dependencies, key: Optional[Key] = None
) -> None:
    return use_resource(ctx, effect, dependencies, key)


@frozen
class AsyncSuccess(Generic[T]):
    value: T


@frozen
class AsyncFailure:
    exception: BaseException


@frozen
class AsyncRunning:
    pass


@frozen
class AsyncCancelled:
    pass


AsyncResult = AsyncSuccess[T] | AsyncFailure | AsyncRunning | AsyncCancelled

_ASYNC_RUNNING = AsyncRunning()
_ASYNC_CANCELLED = AsyncCancelled()


@frozen
class UseAsync(RuntimeCallableProps[AsyncResult[T]], Generic[T]):
    awaitable_factory: Callable[[], Awaitable[T]] = field(eq=False)
    dependencies: Dependencies
    loop: Optional[asyncio.AbstractEventLoop] = field(eq=False, default=None)

    def __call__(self, ctx: CallContext) -> AsyncResult[T]:
        async_result, set_async_result = use_state(ctx, cast(AsyncResult[T], _ASYNC_RUNNING), key="result")

        def construct_awaitable(on_dispose: OnDispose) -> asyncio.Task[T]:
            def on_done(task: asyncio.Task[T]):
                if task.cancelled():
                    set_async_result(_ASYNC_CANCELLED)
                elif (exception := task.exception()) is not None:
                    set_async_result(AsyncFailure(exception))
                else:
                    set_async_result(AsyncSuccess(task.result()))

            awaitable = self.awaitable_factory()

            task: asyncio.Task[T] = asyncio.ensure_future(awaitable, loop=self.loop)
            task.add_done_callback(on_done)
            on_dispose(task.cancel)
            return task

        use_resource(ctx, construct_awaitable, self.dependencies, key="task")

        return async_result


def use_async(
    ctx: CallContext,
    awaitable_factory: Callable[[], Awaitable[T]],
    dependencies: Dependencies,
    loop: Optional[asyncio.BaseEventLoop] = None,
    key: Optional[Key] = None,
) -> AsyncResult[T]:
    return ctx.evaluate_child(UseAsync(awaitable_factory, dependencies, loop), key=key)
