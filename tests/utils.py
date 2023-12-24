from typing import Callable, TypeVar

from attr import frozen

from pybt2.runtime.fibre import Fibre, FibreNode, FibreNodeState
from pybt2.runtime.function_call import CallContext, RuntimeCallableProps
from pybt2.runtime.types import ResultT, StateT, UpdateT

CallableProps = Callable[[CallContext], ResultT]

T = TypeVar("T")


def run_in_fibre(
    fibre: Fibre, fibre_node: FibreNode[CallableProps[ResultT], ResultT, StateT, UpdateT]
) -> Callable[[CallableProps[ResultT]], FibreNodeState[CallableProps[ResultT], ResultT, StateT]]:
    def inner(props: CallableProps[ResultT]) -> FibreNodeState[CallableProps[ResultT], ResultT, StateT]:
        return fibre.run(fibre_node, props)

    return inner


@frozen
class ReturnArgument(RuntimeCallableProps[T]):
    value: T

    def __call__(self, ctx: CallContext) -> T:
        return self.value
