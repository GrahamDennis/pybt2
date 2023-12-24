from typing import Callable, Collection

import pytest
from attr import frozen

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext, FunctionFibreNodeType, RuntimeCallableFunction
from pybt2.runtime.types import Key

from .instrumentation import CallRecordingInstrumentation


@pytest.fixture()
def known_keys() -> Collection[Key]:
    return ()


@pytest.fixture()
def test_instrumentation(known_keys: Collection[Key]) -> CallRecordingInstrumentation:
    return CallRecordingInstrumentation(known_keys=known_keys)


@pytest.fixture()
def fibre(test_instrumentation: CallRecordingInstrumentation) -> Fibre:
    return Fibre(instrumentation=test_instrumentation)


@frozen
class CallableWrapper(RuntimeCallableFunction[Callable[[CallContext], None], None]):
    def __call__(self, ctx: CallContext, props: Callable[[CallContext], None]) -> None:
        return props(ctx)


@pytest.fixture()
def root_fibre_node() -> FibreNode:
    return FibreNode(parent=None, key="root", fibre_node_type=FunctionFibreNodeType(CallableWrapper()))
