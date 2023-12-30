from abc import ABCMeta, abstractmethod
from typing import Generic, Iterator, Optional, final

from typing_extensions import Self

from pybt2.runtime.fibre import CallContext
from pybt2.runtime.types import FibreNodeFunction, FibreNodeState, ResultT


class RuntimeCallableProps(FibreNodeFunction[ResultT, None, None], Generic[ResultT], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext) -> ResultT:
        ...

    @final
    def run(
        self,
        ctx: CallContext,
        previous_state: Optional[FibreNodeState[Self, ResultT, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, ResultT, None]:
        result = self(ctx)

        return ctx.create_fibre_node_state(self, result, None)
