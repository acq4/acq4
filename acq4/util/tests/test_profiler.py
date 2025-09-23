#!/usr/bin/env python3
"""
Unit tests for the new profiler module (acq4.util.profiler)

Tests based on the __main__ example to verify:
1. Correct call tree structure
2. Accurate timing measurements
3. Proper percentage calculations
4. Caller/subcall relationships
"""

import pytest
import time
import threading
from typing import Dict, List, Tuple
from acq4.util.profiler import Profile, ProfileAnalyzer, CallRecord



def sleep_wrapper(sleep_time=0.1):
    """Wrapper function that calls time.sleep"""
    time.sleep(sleep_time)

def _test_function_a():  # 3 calls
    """Function that calls sleep_wrapper twice"""
    sleep_wrapper(0.1)  # Expected: ~100ms
    sleep_wrapper(0.2)  # Expected: ~200ms
    # Total expected: ~300ms

def _test_function_b():  # 1 call, 5 sleeps
    """Function that calls sleep and _test_function_a"""
    time.sleep(0.1)          # Expected: ~100ms (direct C:sleep)
    sleep_wrapper(0.3)  # Expected: ~300ms (via sleep_wrapper)
    time.sleep(0.1)          # Expected: ~100ms (direct C:sleep)
    _test_function_a()   # Expected: ~300ms (calls sleep_wrapper twice)
    # Total expected: ~800ms

def func_to_profile():
    thread = threading.Thread(target=_test_function_a)
    thread.start()

    _test_function_a()   # ~300ms
    _test_function_b()   # ~800ms

    thread.join()




expected_results = {
    'sleep': {
        'n_calls': 9,
        'total_duration': 1.4,
        'avg_duration': 0.155,
        'min_duration': 0.1,
        'max_duration': 0.3,
        'percentage': 127,  # >100% because called multiple times from different threads
        'callers': {
            'sleep_wrapper': 
                {'n_calls': 7, 'total_duration': 1.2, 'avg_duration': 0.17, 'min_duration': 0.1, 'max_duration': 0.3, 'percentage': 100}, 
            '_test_function_b': 
                {'n_calls': 2, 'total_duration': 0.2, 'avg_duration': 0.1, 'min_duration': 0.1, 'max_duration': 0.1, 'percentage': 25},
        },
        'subcalls': {},
    },
    'sleep_wrapper': {
        'n_calls': 7,
        'total_duration': 1.2,
        'avg_duration': 0.17,
        'min_duration': 0.1,
        'max_duration': 0.3,
        'percentage': 108,  # >100% because called multiple times from different threads
        'callers': {
            '_test_function_a': 
                {'n_calls': 6, 'total_duration': 0.9, 'avg_duration': 0.15, 'min_duration': 0.1, 'max_duration': 0.2, 'percentage': 100},
            '_test_function_b': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 37.5},
        },
        'subcalls': {
            'sleep': 
                {'n_calls': 7, 'total_duration': 1.2, 'avg_duration': 0.17, 'min_duration': 0.1, 'max_duration': 0.3, 'percentage': 100},
        },
    },
    '_test_function_a': {
        'n_calls': 3,
        'total_duration': 0.9,
        'avg_duration': 0.3,
        'min_duration': 0.3,
        'max_duration': 0.3,
        'percentage': 82,
        'callers': {
            'Thread.run': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 100},
            '_test_function_b': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 37.5},
            'func_to_profile': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 27},
        },
        'subcalls': {
            'sleep_wrapper': 
                {'n_calls': 6, 'total_duration': 0.9, 'avg_duration': 0.15, 'min_duration': 0.1, 'max_duration': 0.2, 'percentage': 100},
        },
    },
    '_test_function_b': {
        'n_calls': 1,
        'total_duration': 0.8,
        'avg_duration': 0.8,
        'min_duration': 0.8,
        'max_duration': 0.8,
        'percentage': 73,
        'callers': {
            'func_to_profile': 
                {'n_calls': 1, 'total_duration': 0.8, 'avg_duration': 0.8, 'min_duration': 0.8, 'max_duration': 0.8, 'percentage': 73},
        },
        'subcalls': {
            'sleep': 
                {'n_calls': 2, 'total_duration': 0.2, 'avg_duration': 0.1, 'min_duration': 0.1, 'max_duration': 0.1, 'percentage': 25},
            'sleep_wrapper': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 37.5},
            '_test_function_a': 
                {'n_calls': 1, 'total_duration': 0.3, 'avg_duration': 0.3, 'min_duration': 0.3, 'max_duration': 0.3, 'percentage': 37.5},
        },
    },
}



class TestProfiler:
    """Test the new profiler functionality"""


    @pytest.fixture(scope="class")
    def profiled_execution(self) -> ProfileAnalyzer:
        """Execute the same pattern as __main__ and return profiler results"""
        profiler = Profile()
        profiler.start()

        func_to_profile()

        profiler.stop()

        # Analyze results
        analyzer = ProfileAnalyzer(profiler)

        return analyzer

    def _find_calls_by_name(self, events, function_name):
        """Find all CallRecord instances with the given function name"""
        results = []

        def search_calls(calls):
            for call in calls:
                if function_name in (call.funcname, call.display_name):
                    results.append(call)
                search_calls(call.children)

        for thread_id, calls in events.items():
            search_calls(calls)

        return results

    def test_call_tree_structure(self, profiled_execution):
        """Test that the call tree structure is correct"""
        analyzer = profiled_execution
        events = analyzer.profile_events

        # find func_to_profile calls
        func_calls = self._find_calls_by_name(events, 'func_to_profile')
        assert len(func_calls) == 1
        func_call = func_calls[0]
        assert len(func_call.children) == 5

        assert func_call.children[2].display_name == '_test_function_a'
        assert func_call.children[3].display_name == '_test_function_b'

        assert [c.display_name for c in func_call.children[2].children] == ['sleep_wrapper', 'sleep_wrapper']
        assert [c.display_name for c in func_call.children[3].children] == ['sleep', 'sleep_wrapper', 'sleep', '_test_function_a']
        assert [c.display_name for c in func_call.children[3].children[3].children] == ['sleep_wrapper', 'sleep_wrapper']
        assert [c.display_name for c in func_call.children[2].children[0].children] == ['sleep']
        assert [c.display_name for c in func_call.children[2].children[1].children] == ['sleep']

    @pytest.mark.parametrize("func_name", expected_results.keys())
    def test_analysis(self, profiled_execution, func_name):
        """Test that the analysis results match expected values"""
        analyzer = profiled_execution
        events = analyzer.profile_events
        
        call_rec = self._find_calls_by_name(events, func_name)[0]
        analysis = analyzer.analyze_function(call_rec)
        assert analysis is not None

        expected = expected_results[func_name]
        assert analysis.total_calls == expected['n_calls']
        assert analysis.total_duration == pytest.approx(expected['total_duration'], rel=0.05)
        assert analysis.avg_duration == pytest.approx(expected['avg_duration'], rel=0.05)
        assert analysis.min_duration == pytest.approx(expected['min_duration'], rel=0.05)
        assert analysis.max_duration == pytest.approx(expected['max_duration'], rel=0.05)
        assert analysis.profile_percentage == pytest.approx(expected['percentage'], rel=0.05)

        # Check callers
        callers = analysis.get_callers_with_percentages()
        assert len(callers) == len(expected['callers'])
        for caller_key, caller_stats in callers.items():
            func_name = caller_key[1] if caller_key[0] == 'c_call' else caller_key[2]
            assert func_name in expected['callers']
            expected_stats = expected['callers'][func_name]
            for k in caller_stats:
                assert caller_stats[k] == pytest.approx(expected_stats[k], rel=0.05)

        # Check subcalls
        subcalls = analysis.get_subcalls_with_percentages()
        assert len(subcalls) == len(expected['subcalls'])
        for subcall_key, subcall_stats in subcalls.items():
            func_name = subcall_key[1] if subcall_key[0] == 'c_call' else subcall_key[2]
            assert func_name in expected['subcalls']
            expected_stats = expected['subcalls'][func_name]
            for k in subcall_stats:
                assert subcall_stats[k] == pytest.approx(expected_stats[k], rel=0.05)
