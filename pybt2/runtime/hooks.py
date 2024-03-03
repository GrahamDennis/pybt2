import asyncio
from typing import Awaitable, Callable, Generic, Iterator, Optional, ParamSpec, Tuple, TypeVar, cast

from attr import field, frozen
from typing_extensions import Self, override

from pybt2.runtime.fibre import CallContext
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.types import (
    NO_DEPENDENCIES,
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


@frozen(weakref_slot=False)
class UseStateHook(FibreNodeFunction[UseStateResult[T], None, Reducer[T]], Generic[T]):
    value: T = field(eq=False)
    dependencies: Dependencies = NO_DEPENDENCIES

    @override
    def run(
        self,
        ctx: CallContext,
        previous_state: Optional[FibreNodeState[Self, UseStateResult[T], None]],
        enqueued_updates: Iterator[Reducer[T]],
    ) -> FibreNodeState[Self, UseStateResult[T], None]:
        value: T
        setter: Setter[T]

        if previous_state is not None:
            previous_value, previous_setter = previous_state.result
            setter = previous_setter
            if self.dependencies != previous_state.props.dependencies:
                value = self.value
            else:
                value = previous_value
                for update in enqueued_updates:
                    value = cast(Callable[[T], T], update)(value) if callable(update) else cast(T, update)
            if value == previous_value:
                return previous_state
        else:
            value = self.value

            # ensure we don't capture "ctx" in the 'setter' closure
            fibre_node = ctx.fibre_node
            fibre = ctx.fibre

            def setter(reducer: Reducer[T]) -> None:
                fibre_node.enqueue_update(reducer, fibre)

        return ctx.create_fibre_node_state(props=self, result=(value, setter), state=None)


def use_state(
    ctx: CallContext, value: T, dependencies: Dependencies = NO_DEPENDENCIES, key: Optional[Key] = None
) -> Tuple[T, Setter[T]]:
    return ctx.evaluate_child(UseStateHook(value, dependencies=dependencies), key=key)


UseResourceHookResourceFactory = Callable[[OnDispose], T]
UseResourceHookState = Optional[Task]


@frozen(weakref_slot=False)
class UseResourceHook(FibreNodeFunction[T, UseResourceHookState, None], Generic[T]):
    resource_factory: UseResourceHookResourceFactory[T] = field(eq=False)
    dependencies: Dependencies

    @override
    def run(
        self,
        ctx: CallContext,
        previous_state: Optional[FibreNodeState[Self, T, UseResourceHookState]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, T, UseResourceHookState]:
        if previous_state is not None:
            if previous_state.props.dependencies == self.dependencies:
                return previous_state
            else:
                self.dispose(previous_state)

        result, dispose = self.construct_resource(self.resource_factory)

        return ctx.create_fibre_node_state(self, result, dispose)

    @staticmethod
    def construct_resource(resource_factory: UseResourceHookResourceFactory[T]) -> tuple[T, Optional[Task]]:
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
    @override
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


@frozen(weakref_slot=False)
class AsyncSuccess(Generic[T]):
    value: T


@frozen(weakref_slot=False)
class AsyncFailure:
    exception: BaseException


@frozen(weakref_slot=False)
class AsyncRunning:
    pass


@frozen(weakref_slot=False)
class AsyncCancelled:
    pass


AsyncResult = AsyncSuccess[T] | AsyncFailure | AsyncRunning | AsyncCancelled

_ASYNC_RUNNING = AsyncRunning()
_ASYNC_CANCELLED = AsyncCancelled()


@frozen(weakref_slot=False)
class UseAsync(RuntimeCallableProps[AsyncResult[T]], Generic[T]):
    awaitable_factory: Callable[[], Awaitable[T]] = field(eq=False)
    dependencies: Dependencies
    loop: Optional[asyncio.AbstractEventLoop] = field(eq=False, default=None, repr=False)

    def __call__(self, ctx: CallContext) -> AsyncResult[T]:
        async_result, set_async_result = use_state(
            ctx, cast(AsyncResult[T], _ASYNC_RUNNING), dependencies=self.dependencies, key="result"
        )

        def construct_awaitable(on_dispose: OnDispose) -> asyncio.Task[T]:
            def on_done(completed_task: asyncio.Task[T]) -> None:
                if completed_task.cancelled():
                    set_async_result(_ASYNC_CANCELLED)
                elif (exception := completed_task.exception()) is not None:
                    set_async_result(AsyncFailure(exception))
                else:
                    set_async_result(AsyncSuccess(completed_task.result()))

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
