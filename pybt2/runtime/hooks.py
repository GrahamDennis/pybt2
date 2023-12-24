from typing import Any, Callable, Generic, Iterator, Optional, Tuple, TypeVar, cast

from attr import frozen

from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeType
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import NO_PREDECESSORS, FibreNodeResult, Key, Reducer, Setter

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
