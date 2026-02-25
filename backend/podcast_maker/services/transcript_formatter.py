"""
Utilities for formatting transcript data into various formats (JSON, WebVTT, etc.)
"""
import json


def format_transcript_to_json(segments: list) -> str:
    """
    Format transcript segments as JSON string.
    
    Args:
        segments: List of dicts with keys: startMs, endMs, speaker, text
    
    Returns:
        JSON string
    """
    return json.dumps(segments, indent=2, ensure_ascii=False)


def milliseconds_to_vtt_timestamp(ms: int) -> str:
    """
    Convert milliseconds to WebVTT timestamp format (HH:MM:SS.mmm).
    
    Args:
        ms: Time in milliseconds
    
    Returns:
        Formatted timestamp string
    """
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def format_transcript_to_vtt(segments: list) -> str:
    """
    Format transcript segments as WebVTT subtitle file.
    
    Args:
        segments: List of dicts with keys: startMs, endMs, speaker, text
    
    Returns:
        WebVTT formatted string
    """
    vtt_lines = ["WEBVTT\n"]
    
    for i, segment in enumerate(segments, 1):
        start_time = milliseconds_to_vtt_timestamp(segment["startMs"])
        end_time = milliseconds_to_vtt_timestamp(segment["endMs"])
        
        # Format: cue identifier, timestamp, text with speaker
        vtt_lines.append(f"{i}")
        vtt_lines.append(f"{start_time} --> {end_time}")
        vtt_lines.append(f"<v {segment['speaker']}>{segment['text']}")
        vtt_lines.append("")  # Empty line between cues
    
    return "\n".join(vtt_lines)


def format_transcript_to_srt(segments: list) -> str:
    """
    Format transcript segments as SRT subtitle file.
    
    Args:
        segments: List of dicts with keys: startMs, endMs, speaker, text
    
    Returns:
        SRT formatted string
    """
    srt_lines = []
    
    for i, segment in enumerate(segments, 1):
        # SRT uses comma instead of period for milliseconds
        start_time = milliseconds_to_vtt_timestamp(segment["startMs"]).replace(".", ",")
        end_time = milliseconds_to_vtt_timestamp(segment["endMs"]).replace(".", ",")
        
        # Format: sequence number, timestamp, text
        srt_lines.append(str(i))
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(f"{segment['speaker']}: {segment['text']}")
        srt_lines.append("")  # Empty line between cues
    
    return "\n".join(srt_lines)
