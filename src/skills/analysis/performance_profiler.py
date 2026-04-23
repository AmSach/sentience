"""
Performance Profiler Skill
Runtime profiling and performance analysis.
"""

import os
import sys
import time
import cProfile
import pstats
import io
import traceback
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from functools import wraps
from contextlib import contextmanager

METADATA = {
    "name": "performance-profiler",
    "description": "Profile code performance, identify bottlenecks, and measure execution time",
    "category": "analysis",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["profile code", "performance analysis", "measure performance", "find bottlenecks"],
    "dependencies": [],
    "tags": ["performance", "profiling", "optimization", "timing"]
}

SKILL_NAME = "performance-profiler"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "analysis"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class TimingResult:
    name: str
    total_time: float
    calls: int
    avg_time: float
    min_time: float
    max_time: float


class PerformanceProfiler:
    """Code performance profiler with timing and statistics."""
    
    def __init__(self):
        self.timings: Dict[str, List[float]] = {}
        self._profile: Optional[cProfile.Profile] = None
        self._memory_samples: List[Dict[str, Any]] = []
    
    @contextmanager
    def timer(self, name: str):
        """Context manager for timing code blocks."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            if name not in self.timings:
                self.timings[name] = []
            self.timings[name].append(elapsed)
    
    def time_function(self, func: Callable) -> Callable:
        """Decorator to time a function."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                name = func.__name__
                if name not in self.timings:
                    self.timings[name] = []
                self.timings[name].append(elapsed)
        return wrapper
    
    def profile_code(self, code: str, globals_dict: Dict = None, locals_dict: Dict = None) -> Dict[str, Any]:
        """Profile a code string and return statistics."""
        self._profile = cProfile.Profile()
        
        # Prepare execution context
        exec_globals = globals_dict or {'__builtins__': __builtins__}
        exec_locals = locals_dict or {}
        
        # Compile and profile
        try:
            compiled = compile(code, '<profiled>', 'exec')
            self._profile.enable()
            exec(compiled, exec_globals, exec_locals)
            self._profile.disable()
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        
        return self._get_profile_stats()
    
    def profile_function(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Profile a function call and return statistics."""
        self._profile = cProfile.Profile()
        
        try:
            self._profile.enable()
            result = func(*args, **kwargs)
            self._profile.disable()
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "return_value": None
            }
        
        stats = self._get_profile_stats()
        stats["return_value"] = result
        return stats
    
    def _get_profile_stats(self) -> Dict[str, Any]:
        """Extract statistics from profiler."""
        if not self._profile:
            return {}
        
        stream = io.StringIO()
        stats = pstats.Stats(self._profile, stream=stream)
        
        # Get top functions by cumulative time
        stats.sort_stats('cumulative')
        stats.print_stats(20)
        
        cumulative_output = stream.getvalue()
        
        # Get top functions by time
        stream.truncate(0)
        stream.seek(0)
        stats.sort_stats('time')
        stats.print_stats(20)
        
        time_output = stream.getvalue()
        
        # Extract function stats
        func_stats = []
        for func, (cc, nc, tt, ct, callers) in stats.stats.items():
            func_stats.append({
                "function": f"{func[2]}:{func[1]}({func[0]})",
                "calls": nc,
                "total_time": tt,
                "cumulative_time": ct,
                "time_per_call": tt / nc if nc > 0 else 0
            })
        
        # Sort by total time
        func_stats.sort(key=lambda x: x["total_time"], reverse=True)
        
        return {
            "success": True,
            "total_calls": stats.total_calls,
            "primitive_calls": stats.prim_calls,
            "total_time": stats.total_tt,
            "top_by_time": func_stats[:10],
            "top_by_cumulative": sorted(func_stats, key=lambda x: x["cumulative_time"], reverse=True)[:10],
            "raw_output": {
                "by_time": time_output,
                "by_cumulative": cumulative_output
            }
        }
    
    def get_timing_stats(self) -> Dict[str, Any]:
        """Get statistics from recorded timings."""
        results = []
        
        for name, times in self.timings.items():
            if not times:
                continue
            
            results.append(TimingResult(
                name=name,
                total_time=sum(times),
                calls=len(times),
                avg_time=sum(times) / len(times),
                min_time=min(times),
                max_time=max(times)
            ))
        
        return {
            "success": True,
            "timings": [
                {
                    "name": t.name,
                    "total_time": t.total_time,
                    "calls": t.calls,
                    "avg_time": t.avg_time,
                    "min_time": t.min_time,
                    "max_time": t.max_time
                }
                for t in sorted(results, key=lambda x: x.total_time, reverse=True)
            ],
            "total_time": sum(t.total_time for t in results),
            "total_calls": sum(t.calls for t in results)
        }
    
    def benchmark(self, func: Callable, iterations: int = 100, *args, **kwargs) -> Dict[str, Any]:
        """Run a function multiple times and collect statistics."""
        times = []
        errors = []
        results = []
        
        for i in range(iterations):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                results.append(result)
            except Exception as e:
                errors.append(str(e))
            finally:
                elapsed = time.perf_counter() - start
                times.append(elapsed)
        
        if not times:
            return {
                "success": False,
                "error": "No successful runs",
                "errors": errors
            }
        
        # Remove outliers (top and bottom 5%)
        sorted_times = sorted(times)
        trim = max(1, len(sorted_times) // 20)
        trimmed = sorted_times[trim:-trim] if trim < len(sorted_times) // 2 else sorted_times
        
        return {
            "success": True,
            "iterations": iterations,
            "successful_runs": len(times) - len(errors),
            "errors": len(errors),
            "times": {
                "total": sum(times),
                "min": min(times),
                "max": max(times),
                "avg": sum(times) / len(times),
                "median": sorted_times[len(sorted_times) // 2],
                "p95": sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 20 else max(times),
                "p99": sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 100 else max(times),
                "trimmed_avg": sum(trimmed) / len(trimmed) if trimmed else 0
            },
            "ops_per_second": 1.0 / (sum(times) / len(times)) if times else 0,
            "sample_results": results[:3] if results else []
        }
    
    def compare_functions(self, funcs: List[Callable], iterations: int = 100, *args, **kwargs) -> Dict[str, Any]:
        """Compare performance of multiple functions."""
        results = {}
        
        for func in funcs:
            name = func.__name__
            results[name] = self.benchmark(func, iterations, *args, **kwargs)
        
        # Rank by average time
        ranked = sorted(
            results.items(),
            key=lambda x: x[1]["times"]["avg"]
        )
        
        return {
            "success": True,
            "rankings": [
                {
                    "rank": i + 1,
                    "name": name,
                    "avg_time": results[name]["times"]["avg"],
                    "ops_per_second": results[name]["ops_per_second"]
                }
                for i, (name, _) in enumerate(ranked)
            ],
            "fastest": ranked[0][0] if ranked else None,
            "slowest": ranked[-1][0] if ranked else None,
            "speedup": ranked[-1][1]["times"]["avg"] / ranked[0][1]["times"]["avg"] if len(ranked) > 1 else 1,
            "details": results
        }


def execute(
    code: str = None,
    function: Callable = None,
    benchmark: bool = False,
    iterations: int = 100,
    compare: List[Callable] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Profile code or function performance.
    
    Args:
        code: Code string to profile
        function: Function to profile
        benchmark: Run benchmark iterations
        iterations: Number of benchmark iterations
        compare: List of functions to compare
    
    Returns:
        Profiling results with timing statistics
    """
    profiler = PerformanceProfiler()
    
    if compare:
        return profiler.compare_functions(compare, iterations)
    
    if function:
        if benchmark:
            return profiler.benchmark(function, iterations)
        return profiler.profile_function(function)
    
    if code:
        return profiler.profile_code(code)
    
    return {
        "success": False,
        "error": "Provide code, function, or compare functions"
    }
