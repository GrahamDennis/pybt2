from typing import Any, Generic, TypeVar, cast

from attr import frozen

from pybt2.runtime.fibre import FibreNode
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import AbstractContextKey, ContextKey, FibreNodeFunction, ResultT

T = TypeVar("T")

DEFAULT_CONTEXT_CHILD_KEY = "__ContextProvider.Child"


def _context_value_key(context_key: ContextKey[T]) -> str:
    return f"__ContextProvider.Value.{context_key.name}"


@frozen(weakref_slot=False)
class ContextValue(RuntimeCallableProps[T], Generic[T]):
    value: T

    def __call__(self, ctx: CallContext) -> T:
        return self.value


@frozen(weakref_slot=False)
class ContextProvider(RuntimeCallableProps[ResultT], Generic[T, ResultT]):
    context_key: ContextKey[T]
    value: T
    child: FibreNodeFunction[ResultT, Any, Any]

    def __call__(self, ctx: CallContext) -> ResultT:
        ctx.evaluate_child(ContextValue(self.value, key=_context_value_key(self.context_key)))
        context_value_node = ctx.get_last_child()
        context_map: dict[AbstractContextKey, FibreNode] = {self.context_key: context_value_node}
        return ctx.evaluate_child(self.child, additional_contexts=context_map)


def use_context(ctx: CallContext, context_key: ContextKey[T]) -> T:
    context_value_fibre_node = cast(
        FibreNode[ContextValue[T], T, None, None], ctx.get_fibre_node_for_context_key(context_key)
    )
    context_value_fibre_node_state = context_value_fibre_node.get_fibre_node_state()
    assert context_value_fibre_node_state is not None
    ctx.add_predecessor(context_value_fibre_node)
    return context_value_fibre_node_state.result
