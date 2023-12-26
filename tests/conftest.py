from typing import Collection

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import Key

from .utils import ExternalFunctionProps

# This is necessary to get pretty assertion failure messages from the test instrumentation module
pytest.register_assert_rewrite("tests.instrumentation")

from .instrumentation import CallRecordingInstrumentation  # noqa: E402


@pytest.fixture()
def known_keys(request: pytest.FixtureRequest) -> Collection[Key]:
    marker = request.node.get_closest_marker("known_keys")
    if marker is None:
        return ()
    return tuple(marker.args)


@pytest.fixture()
def test_instrumentation(known_keys: Collection[Key]) -> CallRecordingInstrumentation:
    return CallRecordingInstrumentation(known_keys=known_keys)


@pytest.fixture()
def fibre(test_instrumentation: CallRecordingInstrumentation) -> Fibre:
    return Fibre(instrumentation=test_instrumentation)


@pytest.fixture()
def non_incremental_fibre(test_instrumentation: CallRecordingInstrumentation) -> Fibre:
    return Fibre(instrumentation=test_instrumentation, disable_incremental=True)


@pytest.fixture()
def root_fibre_node() -> FibreNode:
    return FibreNode(key="root", parent=None, props_type=ExternalFunctionProps)
