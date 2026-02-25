import io
import os
import re
import sys
from pathlib import Path
from google.cloud import texttospeech
import html
from dotenv import load_dotenv
from pydub import AudioSegment
from podcast_maker.core.logging_config import get_logger

logger = get_logger()

# https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types
MALE_VOICE_CHIRPHD = "en-US-Chirp3-HD-Algenib"
PUCK_VOICE_CHIRPHD = "en-US-Chirp3-HD-Puck"
FEMALE_VOICE_CHIRPHD = "en-US-Chirp3-HD-Aoede"
FEMALE_VOICE_CHIRPHD2 = "en-US-Chirp3-HD-Laomedeia"

MALE_VOICE_STUDIO = "en-US-Studio-Q"
FEMALE_VOICE_STUDIO = "en-US-Studio-O"

class GoogleTTS:
    def __init__(self, google_tts_key):
        self.default_voice = MALE_VOICE_CHIRPHD
        self.client = texttospeech.TextToSpeechClient(
            client_options={"api_key": google_tts_key}
        )
        self.emotion_map = {
            "neutral": {"rate": "medium", "pitch": "0st"},
            "curious": {"rate": "medium", "pitch": "+2st"},
            "excited": {"rate": "fast", "pitch": "+5st"},
            "enthusiastic": {"rate": "fast", "pitch": "+4st"},
            "contemplative": {"rate": "slow", "pitch": "-2st"},
            "amused": {"rate": "medium", "pitch": "+3st"},
            "surprised": {"rate": "fast", "pitch": "+6st"},
            "shocked": {"rate": "fast", "pitch": "+8st"},
            "concerned": {"rate": "slow", "pitch": "-1st"},
            "thoughtful": {"rate": "slow", "pitch": "0st"},
            "warm": {"rate": "medium", "pitch": "+1st"},
            "serious": {"rate": "slow", "pitch": "-3st"},
            "playful": {"rate": "fast", "pitch": "+4st"},
            "emphatic": {"rate": "medium", "pitch": "+3st"},
        }

    def text_to_speech_not_SSML(self, script: str, voice_dict: dict) -> AudioSegment:
        lines: list[tuple[str, str, str]] = self.split_script_into_lines(script, voice_dict)
        return self.create_full_conversation(lines)

    def text_to_speech_with_timestamps(self, script: str, voice_dict: dict):
        """
        Generate audio with timing information for each line.
        Returns: (AudioSegment, list of transcript segments)
        """
        logger.info("Starting text-to-speech generation with timestamps...")
        lines: list[tuple[str, str, str]] = self.split_script_into_lines(script, voice_dict)
        return self.create_full_conversation_with_timestamps(lines)

    def split_script_into_lines(self, script, voice_dict):
        """
        Splits the script into lines.
        Returns a list of tuples: (text_chunk, voice_name, speaker)
        """
        lines: list[tuple[str, str, str]] = []
        speaker = self.default_voice
        text = ""

        for line in script.split("\n"):
            line = line.strip()
            if not line or line.startswith('---'):
                continue
            
            # Match: HOST_1: [emotion] text
            match = re.match(r'(HOST_[12]):\s*\[(.+?)\]\s*(.+)', line)
            if match:
                speaker, emotion, text = match.groups()
                voice_name = voice_dict.get(speaker, self.default_voice)
                lines.append((self._clean_line(text.strip()), voice_name, speaker))
            else:
                print(f"Line did not match expected format: {line}")
                text += line + " "

        return lines
    
    def _clean_line(self, line: str) -> str:
        """
        check the line for a non-speakable chars and remove them.
        """
        # Remove non-speakable characters (e.g., special symbols, control characters)
        cleaned = re.sub(r'[^\w\s\.\,\!\?\;\:\-\']', '', line)
        return cleaned.strip()

    def create_full_conversation(self, dialogue_lines) -> AudioSegment:
        """
        Receives a list of tuples (text, voice_name) and merges them.
        Example dialogue_lines: [("Hello!", "voice_a"), ("Hi there.", "voice_b")]
        """
        char_used = 0
        combined_audio = AudioSegment.empty()
        
        # Crossfade duration in milliseconds to make transitions smoother
        crossfade_ms = 100 
        # Optional: Add a small silence between speakers
        silence_gap = AudioSegment.silent(duration=300)

        for text, voice in dialogue_lines:
            try:            
                current_chunk = self.generate_audio_chunk(text, voice)
                char_used += len(text.encode('utf-8'))
            except Exception as e:
                logger.error(f"Error generating audio for text: '{text}' with voice: '{voice}'. Error: {e}")
                return combined_audio
            
            if len(combined_audio) > 0:
                combined_audio = combined_audio + silence_gap + current_chunk
            else:
                combined_audio = current_chunk
        
        logger.info(f"Done generating audio for conversation. Total characters: {char_used}")
        return combined_audio

    def create_full_conversation_with_timestamps(self, dialogue_lines) -> tuple[AudioSegment, list[dict]]:
        """
        Receives a list of tuples (text, voice_name, speaker) and merges them while tracking timestamps.
        Returns: (AudioSegment, list of transcript segments)
        Each segment: {"startMs": int, "endMs": int, "speaker": str, "text": str}
        """
        char_used = 0
        combined_audio = AudioSegment.empty()
        transcript_segments: list[dict] = []
        
        silence_gap = AudioSegment.silent(duration=300)
        silence_duration_ms = 300

        for text, voice, speaker in dialogue_lines:
            try:            
                start_ms = len(combined_audio)
                current_chunk = self.generate_audio_chunk(text, voice)
                char_used += len(text.encode('utf-8'))
                
                # Add to combined audio
                if len(combined_audio) > 0:
                    combined_audio = combined_audio + silence_gap + current_chunk
                    # Add silence to start time
                    start_ms += silence_duration_ms
                else:
                    combined_audio = current_chunk
                
                end_ms = len(combined_audio)
                
                # Record timestamp
                transcript_segments.append({
                    "startMs": start_ms,
                    "endMs": end_ms,
                    "speaker": speaker,
                    "text": text
                })
                
            except Exception as e:
                logger.error(f"Error generating audio for text: '{text}' with voice: '{voice}'. Error: {e}")
                return combined_audio, transcript_segments
        
        logger.info(f"Done generating audio with timestamps. Total characters: {char_used}, Segments: {len(transcript_segments)}")
        return combined_audio, transcript_segments
    
    def generate_audio_chunk(self, text, voice_name, language_code="en-US"):
        """
        Synthesizes a single chunk of text into an AudioSegment.
        """
        # Configure the synthesis input
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Build the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name
        )

        # Select the type of audio file you want returned
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        # Perform the text-to-speech request
        response = self.client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        # Convert the raw bytes from Google into a pydub AudioSegment
        # We use BytesIO to handle the data in memory
        return AudioSegment.from_file(io.BytesIO(response.audio_content), format="mp3")

    def format_to_SSML(self, script: str, voice_dict: dict) -> list:
        speaker, emotion, text = "HOST_1", "neutral", ""
        ssml_segments = []
        for line in script.split("\n"):
            line = line.strip()
            if not line or line.startswith('---'):
                continue
            
            # Match: HOST_1: [emotion] text
            match = re.match(r'(HOST_[12]):\s*\[(.+?)\]\s*(.+)', line)
            if match:
                speaker, emotion, text = match.groups()
            else:
                print(f"Line did not match expected format: {line}")
                text = line
                # keep emotion and speaker as the last line
            
            # Handle emphasis markers (e.g., **text** or *text*)
            text = re.sub(r'\*\*(.+?)\*\*', r'<emphasis level="strong">\1</emphasis>', text)
            text = re.sub(r'\*(.+?)\*', r'<emphasis level="moderate">\1</emphasis>', text)
            
            # Get emotion settings
            settings = self.emotion_map.get(emotion, self.emotion_map["neutral"])
            
            # Escape special characters
            escaped_text = html.escape(text)
            
            # Get voice for this speaker
            voice_name = voice_dict.get(speaker, self.default_voice)

            # Create SSML
            ssml = f"""<voice name="{voice_name}">
<prosody rate="{settings['rate']}" pitch="{settings['pitch']}">
{escaped_text}
</prosody>
<break time="300ms"/>
</voice>\n"""
            
            ssml_segments.append(ssml)
            
        return ssml_segments

    def generate_chunk_from_SSML(self, ssml_text: str) -> bytes:

        input_text = texttospeech.SynthesisInput(ssml=ssml_text)

        # Configure the voice fallback
        # Note: The 'name' here acts as a default, but the SSML tags will override it
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=self.default_voice
        )
        # Audio configuration (MP3 is standard)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            effects_profile_id=['telephony-class-application'] # Optional: improves clarity for phone-like audio
        )

        # Step 6: Send the request
        response = self.client.synthesize_speech(
            input=input_text, 
            voice=voice, 
            audio_config=audio_config
        )

        return response.audio_content
    
    def text_to_speech_SSML(self, script: str, voice_dict: dict) -> AudioSegment:
        ssml_segments = self.format_to_SSML(script, voice_dict)
        combined_audio = AudioSegment.empty()
        
        current_batch = []
        byte_count = 0 
        MAX_BYTES = 4500 
    
        for segment in ssml_segments:
            segment_bytes = len(segment.encode('utf-8'))
            
            # If adding this segment exceeds limit, process current batch
            if byte_count + segment_bytes > MAX_BYTES and current_batch:
                ssml_text = "<speak>" + "".join(current_batch) + "</speak>"
                

                final_bytes = len(ssml_text.encode('utf-8'))
                print(f"Processing batch: {final_bytes} bytes")
                
                try:
                    audio = self.generate_chunk_from_SSML(ssml_text)
                except Exception as e :
                    print(f"Error processing batch: {e}")
                    print(f"SSML that caused error: {ssml_text}")
                    return combined_audio
            

                current_segment = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
                combined_audio += current_segment
            
                # Reset for next batch
                current_batch = [segment]
                byte_count = segment_bytes
            else:
                current_batch.append(segment)
                byte_count += segment_bytes
    
        # Process remaining batch
        if current_batch:
            ssml_text = "<speak>" + "".join(current_batch) + "</speak>"
            final_bytes = len(ssml_text.encode('utf-8'))
            print(f"Processing final batch: {final_bytes} bytes")
            
            try:
                audio = self.generate_chunk_from_SSML(ssml_text)
            except Exception as e :
                print(f"Error processing batch: {e}")
                print(f"SSML that caused error: {ssml_text}")
                return combined_audio
            current_segment = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
            combined_audio += current_segment

        return combined_audio


if __name__ == "__main__":
    # Add backend directory to Python path when running as standalone script
    backend_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(backend_root))

    from podcast_maker.core.paths import BACKEND_ROOT

    load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
    key = os.getenv("GOOGLE_TTS_KEY")
    client = texttospeech.TextToSpeechClient(
            client_options={"api_key": key}
        )
        
    sample_ssml = "<speak>"
    voice_name = MALE_VOICE_CHIRPHD
    for emotion, settings in GoogleTTS(key).emotion_map.items():
        sample_ssml += f"""
  <voice name="{voice_name}">
    <prosody rate="{settings['rate']}" pitch="{settings['pitch']}"> 
        This is a sample sentence spoken with the emotion: {emotion}.
    </prosody>
  </voice>
  """
        voice_name = FEMALE_VOICE_CHIRPHD if voice_name == MALE_VOICE_CHIRPHD else MALE_VOICE_CHIRPHD
    sample_ssml += "</speak>"
    
    chirp_hd_voices = [
        (MALE_VOICE_CHIRPHD, "Mike"),
        (PUCK_VOICE_CHIRPHD, "Alex"),
        (FEMALE_VOICE_CHIRPHD, "Sarah"),
        (FEMALE_VOICE_CHIRPHD2, "Emma"),
    ]

    for voice_name, voice_label in chirp_hd_voices:
        sample_text = f"Hi, i'm {voice_label} and this is my voice! Lets make some noises."
        ssml = f'<speak><voice name="{voice_name}">{sample_text}</voice></speak>'
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name=voice_name,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            ),
        )
        output_file = f"sample_{voice_label}.mp3"
        with open(output_file, "wb") as out:
            out.write(response.audio_content)
        print(f"Saved: {output_file}")

    # # Step 3: Prepare the synthesis input
    # input_text = texttospeech.SynthesisInput(text="This is a simple test of the Google Text-to-Speech API. We will generate audio from this text and save it as an MP3 file.")

    # # Step 4: Configure the voice fallback
    # # Note: The 'name' here acts as a default, but the SSML tags will override it
    # voice = texttospeech.VoiceSelectionParams(
    #     language_code="en-US",
    #     name="en-US-Chirp3-HD-Puck",
    # )
    # # Step 5: Audio configuration (MP3 is standard)
    # audio_config = texttospeech.AudioConfig(
    #     audio_encoding=texttospeech.AudioEncoding.MP3,
    #     effects_profile_id=['telephony-class-application'] # Optional: improves clarity for phone-like audio
    # )

    # # Step 6: Send the request
    # response = client.synthesize_speech(
    #     input=input_text, 
    #     voice=voice, 
    #     audio_config=audio_config
    # )

    # # Step 7: Write the output to a file
    # output_file = "cs_conversation.mp3"
    # with open(output_file, "wb") as out:
    #     out.write(response.audio_content)
    # print(f'Success! Audio saved to {output_file}')

