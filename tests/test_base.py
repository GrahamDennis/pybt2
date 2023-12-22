from typing import Generic, TypeVar

from attr import frozen

from pybt2.base import NAME
from pybt2.runtime.function_call import (
    CallContext,
    RuntimeCallableFunction,
)

T = TypeVar("T")


@frozen
class ReturnArgument(RuntimeCallableFunction[T, T]):
    def __call__(self, ctx: CallContext, props: T) -> T:
        return props


@frozen
class ReturnArgumentV2(Generic[T]):
    value: T

    def __call__(self, ctx: CallContext) -> T:
        return self.value


def test_base():
    assert NAME == "pybt2"


def test_trivial():
    # root_fibre_node = FibreNode(
    #     parent=None, key="root", fibre_node_type=FunctionFibreNodeType.create_from_callable_type(ReturnArgumentV2)
    # )
    # fibre = Fibre(root=root_fibre_node)

    # desired syntax
    # with root_fibre_node.create_evaluation_context() as ctx:
    #     assert ctx.evaluate(ReturnArgumentV2(1)) == 1
    pass
