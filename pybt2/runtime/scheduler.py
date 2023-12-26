from abc import ABCMeta, abstractmethod
from collections import deque
from typing import Generator, Generic, TypeVar

from attr import Factory, frozen, mutable

YieldType = TypeVar("YieldType", covariant=True)
SendType = TypeVar("SendType", contravariant=True)
ReturnType = TypeVar("ReturnType", covariant=True)


@frozen
class BaseGeneratorCall(Generic[YieldType, SendType, ReturnType], metaclass=ABCMeta):
    stack: list[Generator]
    generator: Generator[YieldType, SendType, ReturnType]

    @abstractmethod
    def __call__(self) -> YieldType:
        ...


@frozen
class SendValue(BaseGeneratorCall[YieldType, SendType, ReturnType], Generic[YieldType, SendType, ReturnType]):
    value: SendType

    def __call__(self) -> YieldType:
        return self.generator.send(self.value)


@frozen
class RaiseException(BaseGeneratorCall[YieldType, SendType, ReturnType], Generic[YieldType, SendType, ReturnType]):
    exception: Exception

    def __call__(self) -> YieldType:
        return self.generator.throw(self.exception)


GeneratorCall = SendValue | RaiseException


@mutable
class Scheduler:
    _queue: deque[GeneratorCall] = Factory(deque)

    def schedule(self, generator: Generator) -> None:
        self._queue.append(SendValue(stack=[], generator=generator, value=None))

    def run(self) -> None:
        while self._queue:
            generator_call = self._queue.popleft()
            try:
                result = generator_call()

                if isinstance(result, Generator):
                    stack = generator_call.stack
                    stack.append(generator_call.generator)
                    self._queue.append(SendValue(stack=stack, generator=result, value=None))
                elif generator_call.stack:
                    parent_stack = generator_call.stack
                    parent_generator = parent_stack.pop()
                    self._queue.append(SendValue(stack=parent_stack, generator=parent_generator, value=result))
            except StopIteration as err:
                if generator_call.stack:
                    parent_stack = generator_call.stack
                    parent_generator = parent_stack.pop()
                    self._queue.append(SendValue(stack=parent_stack, generator=parent_generator, value=err.value))
                else:
                    # Nothing left to handle, just drop
                    pass
            except Exception as err:
                if generator_call.stack:
                    parent_stack = generator_call.stack
                    parent_generator = parent_stack.pop()
                    self._queue.append(RaiseException(stack=parent_stack, generator=parent_generator, exception=err))
                else:
                    # Nothing left to handle, just raise it
                    raise
