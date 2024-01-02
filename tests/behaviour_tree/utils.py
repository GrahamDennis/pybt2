from typing import Callable

from attr import frozen

from pybt2.behaviour_tree.types import BTNode, BTNodeResult, Result
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.types import FibreNodeState

ExternalBTNodeFunction = Callable[[CallContext], BTNodeResult]


@frozen
class ExternalBTNode(BTNode):
    _fn: ExternalBTNodeFunction

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return self._fn(ctx)


def run_node_in_fibre(
    fibre: Fibre, fibre_node: FibreNode[ExternalBTNode, Result, None, None], drain_work_queue: bool = False
) -> Callable[[ExternalBTNodeFunction], FibreNodeState[ExternalBTNode, Result, None]]:
    def inner(fn: ExternalBTNodeFunction) -> FibreNodeState[ExternalBTNode, Result, None]:
        result = fibre.run(fibre_node, ExternalBTNode(fn))
        if drain_work_queue:
            fibre.drain_work_queue()
        return result

    return inner
