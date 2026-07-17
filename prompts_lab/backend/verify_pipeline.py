"""
Verification Script for Prompt Pipeline Backend.
Tests the Gemini Adapter and the pipeline executor engine.
"""

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Setup path and load environment
BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

from services.gemini import GeminiAdapter
from engine.executor import PipelineExecutor
from engine.validator import validate_pipeline_data


def test_llm_adapter():
    print("\n=== Testing LLM Gemini Adapter ===")
    
    # Initialize the adapter
    try:
        # Defaults to gemini-2.5-flash
        llm = GeminiAdapter()
        print(f"Successfully initialized GeminiAdapter with model: {llm.model}")
    except Exception as e:
        print(f"Failed to initialize GeminiAdapter: {e}")
        return False

    # Test get_tokens() initially
    print(f"Initial tokens count: {llm.get_tokens()}")

    # 1. Test generate_text
    print("\n1. Testing generate_text...")
    try:
        resp = llm.generate_text("Say 'Hello Prompts Lab' in exactly 3 words.", temperature=0.0)
        print(f"Response: '{resp.text.strip()}'")
        print(f"Usage for this call: {resp.usage}")
        print(f"Accumulated tokens: {llm.get_tokens()}")
    except Exception as e:
        print(f"generate_text failed: {e}")
        return False

    # 2. Test generate_json
    print("\n2. Testing generate_json...")
    try:
        json_prompt = (
            "Output a JSON object with two fields: 'greeting' (value 'hello') and 'year' (value 2026). "
            "Do not include any formatting other than clean JSON."
        )
        resp_json = llm.generate_json(json_prompt, temperature=0.0)
        print(f"Raw Text: '{resp_json.text.strip()}'")
        print(f"Parsed JSON: {resp_json.json_data}")
        print(f"Usage for this call: {resp_json.usage}")
        print(f"Accumulated tokens: {llm.get_tokens()}")
    except Exception as e:
        print(f"generate_json failed: {e}")
        return False

    # 3. Test generate_follow_up
    print("\n3. Testing generate_follow_up (correction chat)...")
    try:
        history = [
            {"role": "user", "text": "Who is the primary host profile?"},
            {"role": "model", "text": "We have Sarah who is curious."}
        ]
        resp_chat = llm.generate_follow_up(
            history=history,
            follow_up_message="What is her speaking style?",
            temperature=0.0
        )
        print(f"Follow up Response: '{resp_chat.text.strip()}'")
        print(f"Usage for this call: {resp_chat.usage}")
        print(f"Total accumulated tokens: {llm.get_tokens()}")
    except Exception as e:
        print(f"generate_follow_up failed: {e}")
        return False

    return True


def test_pipeline_execution():
    print("\n=== Testing Pipeline YAML Execution ===")
    
    # Define a simple mockup pipeline yaml programmatically
    mock_pipeline = {
        "version": 1,
        "id": "verify_test_pipeline",
        "name": "Verification Test Pipeline",
        "description": "A lightweight pipeline to test execution parsing, placeholder binding, and mapped looping.",
        "defaults": {
            "model": {
                "provider": "gemini",
                "name": "gemini-2.5-flash"
            },
            "failure": {
                "strategy": "retry",
                "max_attempts": 2
            }
        },
        "inputs": {
            "topic": {
                "type": "text",
                "required": True
            }
        },
        "stages": [
            {
                "id": "planner",
                "type": "llm",
                "execution": "single",
                "prompt": {
                    "source": "inline",
                    "text": "Plan a short podcast outline about the topic: {{TOPIC}}. Output JSON containing: 'title' (string) and 'topics_list' (array of strings, exactly 2 items)."
                },
                "bindings": [
                    {
                        "placeholder": "{{TOPIC}}",
                        "source": "inputs.topic",
                        "format": "text"
                    }
                ],
                "response": {
                    "kind": "json",
                    "file": "outputs/blueprint.json"
                },
                "outputs": {
                    "blueprint": {
                        "source": "response"
                    },
                    "topics": {
                        "source": "response.topics_list"
                    }
                }
            },
            {
                "id": "expounder",
                "type": "llm",
                "execution": "map",
                "map": {
                    "over": "planner.topics",
                    "item_name": "subtopic"
                },
                "prompt": {
                    "source": "inline",
                    "text": "Write a single paragraph explaining: {{SUBTOPIC}}."
                },
                "bindings": [
                    {
                        "placeholder": "{{SUBTOPIC}}",
                        "source": "item",
                        "format": "text"
                    }
                ],
                "response": {
                    "kind": "text",
                    "per_item_file": "outputs/subtopic_{{ item }}.txt",
                    "aggregate_file": "outputs/aggregate_research.md",
                    "aggregate_strategy": "concat_with_headers"
                },
                "outputs": {
                    "paragraphs": {
                        "source": "response.items"
                    },
                    "full_text": {
                        "source": "response.aggregate"
                    }
                }
            }
        ]
    }

    # Validate
    try:
        validate_pipeline_data(mock_pipeline, BACKEND_ROOT)
        print("Pipeline YAML data validation passed successfully.")
    except Exception as e:
        print(f"Pipeline validation failed: {e}")
        return False

    # Execute
    try:
        inputs = {"topic": "AI in space exploration"}
        runs_root = BACKEND_ROOT / "test_runs"
        
        executor = PipelineExecutor(
            pipeline_data=mock_pipeline,
            inputs=inputs,
            runs_root=runs_root
        )
        
        print("\nStarting pipeline execution...")
        run_dir = executor.run()
        print(f"Pipeline executed successfully. Run saved to: {run_dir}")
        
        # Verify outputs exist
        blueprint_file = run_dir / "outputs" / "blueprint.json"
        aggregate_file = run_dir / "outputs" / "aggregate_research.md"
        manifest_file = run_dir / "run_manifest.json"
        
        print("\nVerifying output files:")
        print(f"Blueprint exists: {blueprint_file.is_file()} (size: {blueprint_file.stat().st_size if blueprint_file.is_file() else 0} bytes)")
        print(f"Aggregate exists: {aggregate_file.is_file()} (size: {aggregate_file.stat().st_size if aggregate_file.is_file() else 0} bytes)")
        print(f"Manifest exists: {manifest_file.is_file()} (size: {manifest_file.stat().st_size if manifest_file.is_file() else 0} bytes)")
        
        # Print stats from manifest
        if manifest_file.is_file():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            print(f"\nManifest stats:")
            print(f"  Topic: {manifest.get('topic')}")
            print(f"  Total prompt tokens: {manifest.get('tokens', {}).get('prompt_tokens')}")
            print(f"  Total response tokens: {manifest.get('tokens', {}).get('response_tokens')}")
            print(f"  Total tokens used: {manifest.get('tokens', {}).get('total_tokens')}")
            
            # Print files created
            print("Files listed in manifest:")
            for record in manifest.get("stage_records", []):
                print(f"  Stage {record.get('stage')}: {record.get('output_files')}")
                
        return True
    except Exception as e:
        print(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=== STARTING BACKEND VERIFICATION ===")
    
    # Check GOOGLE_API_KEY
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not found in environment or .env. Please configure it.")
        sys.exit(1)
        
    llm_ok = test_llm_adapter()
    if not llm_ok:
        print("\nLLM Adapter tests FAILED.")
        sys.exit(1)
        
    pipeline_ok = test_pipeline_execution()
    if not pipeline_ok:
        print("\nPipeline execution tests FAILED.")
        sys.exit(1)
        
    print("\n=== ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ===")
