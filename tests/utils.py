from typing import Callable

from attr import frozen

from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeState
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import ResultT, StateT, UpdateT

ExternalFunction = Callable[[CallContext], ResultT]


@frozen
class ExternalFunctionProps(RuntimeCallableProps[ResultT]):
    _fn: ExternalFunction[ResultT]

    def __call__(self, ctx: CallContext) -> ResultT:
        return self._fn(ctx)


def run_in_fibre(
    fibre: Fibre, fibre_node: FibreNode[ExternalFunctionProps[ResultT], ResultT, StateT, UpdateT]
) -> Callable[[ExternalFunction[ResultT]], FibreNodeState[ExternalFunctionProps[ResultT], ResultT, StateT]]:
    def inner(fn: ExternalFunction[ResultT]) -> FibreNodeState[ExternalFunctionProps[ResultT], ResultT, StateT]:
        return fibre.run(fibre_node, ExternalFunctionProps(fn))

    return inner


@frozen
class ReturnArgument(RuntimeCallableProps[ResultT]):
    value: ResultT

    def __call__(self, ctx: CallContext) -> ResultT:
        return self.value
