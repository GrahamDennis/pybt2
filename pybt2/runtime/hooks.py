from typing import Any, Callable, Generic, Iterator, Optional, Tuple, TypeVar, cast

from attr import field, frozen

from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeType
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import (
    NO_PREDECESSORS,
    Dependencies,
    FibreNodeResult,
    Key,
    OnDispose,
    Reducer,
    Setter,
    Task,
)

T = TypeVar("T")


@frozen
class UseStateHook(FibreNodeType[T, Tuple[T, Setter[T]], None, Reducer[T]], Generic[T]):
    def are_props_equal(self, left: T, right: T) -> bool:
        # Props changing doesn't make this node out of date
        return True

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[T, Tuple[T, Setter[T]], None, Reducer[T]],
        props: T,
        previous_result: Optional[FibreNodeResult[Tuple[T, Setter[T]], None]],
        enqueued_updates: Iterator[Reducer[T]],
    ) -> FibreNodeResult[Tuple[T, Setter[T]], None]:
        value: T
        setter: Setter[T]

        if previous_result is not None:
            previous_value, previous_setter = previous_result.result
            value = previous_value
            setter = previous_setter
            for update in enqueued_updates:
                value = cast(Callable[[T], T], update)(value) if callable(update) else cast(T, update)
            if value == previous_value:
                return previous_result
        else:
            value = props
            setter = fibre_node.enqueue_update
        return FibreNodeResult(
            result=(value, setter),
            result_version=previous_result.result_version + 1 if previous_result is not None else 1,
            state=None,
            predecessors=NO_PREDECESSORS,
        )


_USE_STATE_HOOK_INSTANCE = UseStateHook[Any]()


def use_state(ctx: CallContext, value: T, key: Optional[Key] = None) -> Tuple[T, Setter[T]]:
    return ctx.evaluate_child(value, cast(UseStateHook[T], _USE_STATE_HOOK_INSTANCE), key=key)


UseResourceHookResourceFactory = Callable[[OnDispose], T]


@frozen
class UseResourceHookProps(Generic[T]):
    resource_factory: UseResourceHookResourceFactory[T] = field(eq=False)
    dependencies: Dependencies


@frozen
class UseResourceHookState:
    # If the previous props were supplied, we wouldn't need this
    dependencies: Dependencies
    dispose: Optional[Task]


@frozen
class UseResourceHook(FibreNodeType[UseResourceHookProps[T], T, UseResourceHookState, None], Generic[T]):
    def are_props_equal(self, left: UseResourceHookProps[T], right: UseResourceHookProps[T]) -> bool:
        return left == right

    def run(
        self,
        fibre: "Fibre",
        fibre_node: FibreNode[UseResourceHookProps[T], T, UseResourceHookState, None],
        props: UseResourceHookProps[T],
        previous_result: Optional[FibreNodeResult[T, UseResourceHookState]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeResult[T, UseResourceHookState]:
        if previous_result is not None and previous_result.state.dependencies == props.dependencies:
            return previous_result
        if previous_result is not None and previous_result.state.dispose is not None:
            previous_result.state.dispose()

        result, dispose = self.construct_resource(props.resource_factory)
        result_version: int
        if previous_result is None:
            result_version = 1
        else:
            previous_result_version = previous_result.result_version
            result_version = (
                previous_result_version if result == previous_result.result else previous_result_version + 1
            )

        return FibreNodeResult(
            result=result,
            result_version=result_version,
            state=UseResourceHookState(dependencies=props.dependencies, dispose=dispose),
            predecessors=None,
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


_USE_RESOURCE_HOOK_INSTANCE = UseResourceHook[Any]()


def use_resource(
    ctx: CallContext,
    resource_factory: UseResourceHookResourceFactory[T],
    dependencies: Dependencies,
    key: Optional[Key],
) -> T:
    return ctx.evaluate_child(
        UseResourceHookProps(resource_factory, dependencies),
        cast(UseResourceHook[T], _USE_RESOURCE_HOOK_INSTANCE),
        key=key,
    )
