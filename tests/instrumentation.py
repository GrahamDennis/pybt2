from typing import Collection, Optional

from attr import Factory, field, mutable, setters
from typing_extensions import override

from pybt2.runtime.fibre import FibreNode
from pybt2.runtime.instrumentation import FibreInstrumentation
from pybt2.runtime.types import Key, KeyPath


def to_frozenset(iterable: Collection[Key]) -> frozenset[Key]:
    return frozenset(iterable)


@mutable
class CallRecordingInstrumentation(FibreInstrumentation):
    known_keys: frozenset[Key] = field(converter=to_frozenset, on_setattr=setters.frozen)
    evaluations: list[KeyPath] = Factory(list)

    @override
    def on_node_evaluation_start(self, fibre_node: FibreNode) -> None:
        filtered_key_path = self._get_filtered_key_path(fibre_node)
        if filtered_key_path is not None and (not self.evaluations or self.evaluations[-1] != filtered_key_path):
            self.evaluations.append(filtered_key_path)

    @override
    def on_node_evaluation_end(self, fibre_node: FibreNode) -> None:
        pass

    def _get_filtered_key_path(self, fibre_node: FibreNode) -> Optional[KeyPath]:
        filtered_key_path = tuple(key for key in fibre_node.key_path if key in self.known_keys)
        if filtered_key_path:
            return filtered_key_path
        else:
            return None

    def assert_evaluations_and_reset(self, *expected_evaluations: Optional[KeyPath]) -> None:
        assert self.evaluations == [
            expected_evaluation for expected_evaluation in expected_evaluations if expected_evaluation is not None
        ]
        self.reset()

    def reset(self) -> None:
        self.evaluations.clear()
