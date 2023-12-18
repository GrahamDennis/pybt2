from typing import Generic, TypeVar

from attr import frozen

Key = str | int
KeyPath = tuple[Key, ...]

PropsT = TypeVar("PropsT")
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")
UpdateT = TypeVar("UpdatesT")


@frozen
class CallFrameResult(Generic[ResultT, StateT]):
    result: ResultT
    state: StateT
