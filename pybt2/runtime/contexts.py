from typing import Any, Generic, Mapping, TypeVar, cast

from attr import frozen

from pybt2.runtime.fibre import CallContext, FibreNode
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.types import ContextKey, FibreNodeFunction, ResultT

T = TypeVar("T")


def _context_value_key(context_key: ContextKey[T]) -> str:
    return f"__ContextProvider.Value.{context_key.id}"


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
        context_map: dict[Any, FibreNode] = {self.context_key: context_value_node}
        return ctx.evaluate_child(self.child, additional_contexts=context_map)


@frozen(weakref_slot=False)
class BatchContextProvider(RuntimeCallableProps[ResultT], Generic[ResultT]):
    contexts: Mapping[ContextKey, Any]
    child: FibreNodeFunction[ResultT, Any, Any]

    def __call__(self, ctx: CallContext) -> ResultT:
        context_nodes: dict[Any, FibreNode] = {}
        for context_key, context_value in self.contexts.items():
            ctx.evaluate_child(ContextValue(context_value), key=_context_value_key(context_key))
            context_nodes[context_key] = ctx.get_last_child()
        return ctx.evaluate_child(self.child, additional_contexts=context_nodes)


def use_context(ctx: CallContext, context_key: ContextKey[T]) -> T:
    context_value_fibre_node = cast(FibreNode[ContextValue[T], T, None, None], ctx.fibre_node.contexts[context_key])
    context_value_fibre_node_state = context_value_fibre_node.get_fibre_node_state()
    assert context_value_fibre_node_state is not None
    ctx.add_predecessor(context_value_fibre_node)
    return context_value_fibre_node_state.result
