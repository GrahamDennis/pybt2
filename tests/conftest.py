from typing import Collection

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import Key

from .instrumentation import CallRecordingInstrumentation
from .utils import ExternalFunctionProps


@pytest.fixture()
def known_keys() -> Collection[Key]:
    return ()


@pytest.fixture()
def test_instrumentation(known_keys: Collection[Key]) -> CallRecordingInstrumentation:
    return CallRecordingInstrumentation(known_keys=known_keys)


@pytest.fixture()
def fibre(test_instrumentation: CallRecordingInstrumentation) -> Fibre:
    return Fibre(instrumentation=test_instrumentation)


@pytest.fixture()
def root_fibre_node() -> FibreNode:
    return FibreNode(key="root", parent=None, props_type=ExternalFunctionProps)
