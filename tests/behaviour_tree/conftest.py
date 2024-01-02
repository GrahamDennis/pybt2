from typing import Type

import pytest

from pybt2.runtime.types import FibreNodeFunction
from tests.behaviour_tree.utils import ExternalBTNode


@pytest.fixture()
def root_fibre_node_props_type() -> Type[FibreNodeFunction]:
    return ExternalBTNode
