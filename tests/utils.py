from typing import Any, Callable

from attr import frozen

from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeState
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import FibreNodeFunction, ResultT, StateT, UpdateT

ExternalFunction = Callable[[CallContext], ResultT]


@frozen
class ExternalFunctionProps(RuntimeCallableProps[ResultT]):
    _fn: ExternalFunction[ResultT]

    def __call__(self, ctx: CallContext) -> ResultT:
        return self._fn(ctx)


def run_in_fibre(
    fibre: Fibre,
    fibre_node: FibreNode[ExternalFunctionProps[ResultT], ResultT, StateT, UpdateT],
    drain_work_queue: bool = False,
) -> Callable[[ExternalFunction[ResultT]], FibreNodeState[ExternalFunctionProps[ResultT], ResultT, StateT]]:
    def inner(fn: ExternalFunction[ResultT]) -> FibreNodeState[ExternalFunctionProps[ResultT], ResultT, StateT]:
        result = fibre.run(fibre_node, ExternalFunctionProps(fn))
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
