You are evaluating a podcast script against a human-written goals document.

Read the goals document and the podcast script. Score the script against the goals using dimension names derived from the goals document. Use float scores from 0 to 10, where 10 is excellent.

Return ONLY valid JSON. Do not include a preamble, commentary, markdown fences, or trailing text.

The JSON object must have this shape:

{
  "overall_score": 7.2,
  "dimension_scores": {
    "narrative_quality": 8.0,
    "technical_depth": 6.0,
    "speakability": 7.5,
    "engagement": 7.0,
    "factual_accuracy": 8.0
  },
  "reasoning": "A concise explanation of the scores."
}

The exact dimension names should come from the goals document. Keep `dimension_scores` as an object with string keys and numeric values.

