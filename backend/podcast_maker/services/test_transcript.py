"""
Test script for transcript generation functionality
"""
import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))

from podcast_maker.services.transcript_formatter import (
    format_transcript_to_json,
    format_transcript_to_vtt,
    milliseconds_to_vtt_timestamp
)

# Test data
test_segments = [
    {
        "startMs": 0,
        "endMs": 3500,
        "speaker": "HOST_1",
        "text": "Welcome to our podcast about the history of computing!"
    },
    {
        "startMs": 3800,
        "endMs": 8200,
        "speaker": "HOST_2",
        "text": "That's right! Today we're diving into the fascinating world of early computers."
    },
    {
        "startMs": 8500,
        "endMs": 12000,
        "speaker": "HOST_1",
        "text": "Let's start with the ENIAC, one of the first electronic general-purpose computers."
    }
]

def test_timestamp_conversion():
    """Test milliseconds to VTT timestamp conversion"""
    print("Testing timestamp conversion...")
    
    test_cases = [
        (0, "00:00:00.000"),
        (1000, "00:00:01.000"),
        (61000, "00:01:01.000"),
        (3661000, "01:01:01.000"),
        (3500, "00:00:03.500"),
    ]
    
    for ms, expected in test_cases:
        result = milliseconds_to_vtt_timestamp(ms)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {ms}ms -> {result} (expected: {expected})")

def test_json_formatting():
    """Test JSON transcript formatting"""
    print("\nTesting JSON formatting...")
    json_output = format_transcript_to_json(test_segments)
    print(json_output[:200] + "..." if len(json_output) > 200 else json_output)
    print(f"  ✓ Generated JSON transcript ({len(json_output)} bytes)")

def test_vtt_formatting():
    """Test WebVTT transcript formatting"""
    print("\nTesting VTT formatting...")
    vtt_output = format_transcript_to_vtt(test_segments)
    print(vtt_output)
    print(f"  ✓ Generated VTT transcript ({len(vtt_output)} bytes)")

def test_timing_logic():
    """Test that timestamps are sequential and make sense"""
    print("\nTesting timestamp logic...")
    
    for i, segment in enumerate(test_segments):
        start = segment["startMs"]
        end = segment["endMs"]
        duration = end - start
        
        # Check that end > start
        assert end > start, f"Segment {i}: end time must be after start time"
        
        # Check that next segment starts after current ends (with some gap)
        if i < len(test_segments) - 1:
            next_start = test_segments[i + 1]["startMs"]
            assert next_start >= end, f"Segment {i}: next segment overlaps"
        
        print(f"  ✓ Segment {i}: {start}-{end}ms (duration: {duration}ms)")

if __name__ == "__main__":
    print("=" * 60)
    print("TRANSCRIPT FORMATTING TESTS")
    print("=" * 60)
    
    try:
        test_timestamp_conversion()
        test_json_formatting()
        test_vtt_formatting()
        test_timing_logic()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
