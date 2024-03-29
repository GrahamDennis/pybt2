from typing import Any, Callable, Sequence, cast

from attr import frozen

from pybt2.runtime.fibre import CallContext, Fibre, FibreNode, FibreNodeState
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.types import FibreNodeFunction, ResultT, StateT, UpdateT

ExternalFunction = Callable[[CallContext], ResultT]


@frozen
class ExternalFunctionProps(RuntimeCallableProps[ResultT]):
    _fn: ExternalFunction[ResultT]

    def __call__(self, ctx: CallContext) -> ResultT:
        return self._fn(ctx)


def run_in_fibre(
    fibre: Fibre,
    fibre_node: FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT],
    drain_work_queue: bool = False,
) -> Callable[
    [ExternalFunction[ResultT]], FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT]
]:
    def inner(
        fn: ExternalFunction[ResultT],
    ) -> FibreNodeState[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT]:
        result = fibre.run(
            fibre_node,
            cast(
                Callable[[Callable[[CallContext], ResultT]], FibreNodeFunction[ResultT, StateT, UpdateT]],
                fibre_node.props_type,
            )(fn),
        )
        if drain_work_queue:
            fibre.drain_work_queue()
        return result

    return inner


@frozen
class ReturnArgument(RuntimeCallableProps[ResultT]):
    value: ResultT

    def __call__(self, ctx: CallContext) -> ResultT:
        return self.value


@frozen
class EvaluateChild(RuntimeCallableProps[ResultT]):
    child: FibreNodeFunction[ResultT, Any, Any]

    def __call__(self, ctx: CallContext) -> ResultT:
        return ctx.evaluate_child(self.child)


@frozen
class EvaluateChildren(RuntimeCallableProps[Sequence[ResultT]]):
    children: Sequence[FibreNodeFunction[ResultT, Any, Any]]

    def __call__(self, ctx: CallContext) -> Sequence[ResultT]:
        return tuple(ctx.evaluate_child(child) for child in self.children)
