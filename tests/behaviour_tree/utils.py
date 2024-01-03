from typing import Callable

from attr import frozen

from pybt2.behaviour_tree.types import BTNode, BTNodeResult
from pybt2.runtime.fibre import CallContext

ExternalBTNodeFunction = Callable[[CallContext], BTNodeResult]


@frozen
class ExternalBTNode(BTNode):
    _fn: ExternalBTNodeFunction

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return self._fn(ctx)
