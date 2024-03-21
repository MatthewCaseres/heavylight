from inspect import signature
from typing import Callable

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Tuple, Union

@dataclass(frozen=True)
class FunctionCall:
    func_name: str
    args: tuple
    kwargs: frozenset

ArgsHash = Tuple[Tuple, frozenset]

class CacheGraph:
    def __init__(self):
        self.reset()

    def reset(self):
        self.stack: list[FunctionCall] = [] # what function is currently being called
        self.caches: defaultdict[str, dict[ArgsHash, Any]] = defaultdict(dict) # Results of function calls
        self.graph: defaultdict[FunctionCall, set[FunctionCall]] = defaultdict(set) # Call graph, graph[caller] = [callee1, callee2, ...]
        # Typically aggregated results for a function at a timestep.
        self.stored_results: defaultdict[str, dict[int, Any]] = defaultdict(dict)
        # What is the last function that needs the result of a function? Used to help in clearing the cache
        self.last_needed_by: dict[FunctionCall, FunctionCall] = {}
        # When we call a function, what can be cleared?
        self.can_clear: dict[FunctionCall, list[FunctionCall]] = defaultdict(list)

    def check_if_cached(self, function_call: FunctionCall):
        name_in_cache = function_call.func_name in self.caches
        return name_in_cache and (function_call.args, function_call.kwargs) in self.caches[function_call.func_name]

    def __call__(self, storage_func: Union[Callable, None] = None):
        def decorator_factory(func):
            def wrapper(*args, **kwargs):
                frozen_kwargs = frozenset(kwargs.items())
                function_call = FunctionCall(func.__name__, args, frozen_kwargs)
                if self.stack:
                    self.graph[self.stack[-1]].add(function_call)
                if not self.check_if_cached(function_call):
                    self.stack.append(function_call)
                    result = func(*args, **kwargs)
                    for clearable_call in self.can_clear[function_call]:
                        del self.caches[clearable_call.func_name][(clearable_call.args, clearable_call.kwargs)]
                    self.caches[func.__name__][(args, frozen_kwargs)] = result
                    self._store_result(storage_func, func, args, kwargs, result)
                    self.stack.pop()
                return self.caches[func.__name__][(args, frozen_kwargs)]
            decorator = _Cache(self, wrapper)
            return decorator
        return decorator_factory
    
    def _store_result(self, storage_func: Union[Callable, None], func: Callable, args: tuple, kwargs: dict, raw_result: Any):
        """We might want to store an intermediate result"""
        if storage_func is None:
            return
        # These conditions should not trigger, why we assert and not throw an exception
        assert len(args) == 1 and isinstance(args[0], int)
        assert len(kwargs) == 0
        # store the processed result
        timestep = args[0]
        stored_result = storage_func(raw_result)
        self.stored_results[func.__name__][timestep] = stored_result

class _Cache:
    def __init__(self, cache_graph: CacheGraph, func: Callable):
        self.cache_graph = cache_graph
        self.func = func
        self.single_parameter_t = check_if_single_parameter_t(func)
    
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.func(*args, **kwds)
    
    
def check_if_single_parameter_t(func: Callable):
    sig = signature(func)
    return 't' in sig.parameters and len(sig.parameters) == 1