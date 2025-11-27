#!/usr/bin/env python3
"""
Parse AssemblyAI billing data from React Server Components payload
"""

# Speech-to-Text Models
speech_to_text = {
    "Slam-1": {"rate": 0.27, "unit": "hour", "beta": True},
    "Universal": {"rate": 0.15, "unit": "hour", "beta": False},
    "Nano": {"rate": 0.12, "unit": "hour", "beta": False},
}

# Streaming Speech-to-Text Models
streaming_speech_to_text = {
    "Keyterm Prompting": {"rate": 0.04, "unit": "hour"},
    "Universal-Streaming": {"rate": 0.15, "unit": "hour"},
    "Streaming (legacy)": {"rate": 0.47, "unit": "hour"},
}

# Speech Understanding Features
speech_understanding = {
    "Key Phrases": {"rate": 0.01, "unit": "hour"},
    "PII Audio Redaction": {"rate": 0.05, "unit": "hour"},
    "Summarization": {"rate": 0.03, "unit": "hour"},
    "Auto Chapters": {"rate": 0.08, "unit": "hour"},
    "Translation": {"rate": 0.06, "unit": "hour"},
    "Speaker Identification": {"rate": 0.02, "unit": "hour"},
    "Content Moderation": {"rate": 0.15, "unit": "hour"},
    "Custom Formatting": {"rate": 0.03, "unit": "hour"},
    "Topic Detection": {"rate": 0.15, "unit": "hour"},
    "Sentiment Analysis": {"rate": 0.02, "unit": "hour"},
    "PII Redaction": {"rate": 0.08, "unit": "hour"},
    "Filter Profanity": {"rate": 0.01, "unit": "hour"},
}

# LLM Gateway + LeMUR Input Tokens
llm_input_tokens = {
    "GPT OSS 120b": {"rate": 0.15, "unit": "1M tokens"},
    "Claude Opus 4": {"rate": 15.00, "unit": "1M tokens"},
    "GPT 5": {"rate": 1.25, "unit": "1M tokens"},
    "GPT 5 Mini": {"rate": 0.25, "unit": "1M tokens"},
    "Claude Haiku 4.5": {"rate": 1.00, "unit": "1M tokens"},
    "GPT OSS 20b": {"rate": 0.07, "unit": "1M tokens"},
    "GPT 5 Nano": {"rate": 0.05, "unit": "1M tokens"},
    "Claude 3.5 Haiku": {"rate": 0.80, "unit": "1M tokens"},
    "Claude Sonnet 4.5": {"rate": 3.00, "unit": "1M tokens"},
    "Chatgpt 4o Latest": {"rate": 5.00, "unit": "1M tokens"},
    "GPT 4.1": {"rate": 2.00, "unit": "1M tokens"},
    "Gemini 3 Pro Preview <200k Tokens": {"rate": 2.00, "unit": "1M tokens"},
    "Claude Sonnet 4": {"rate": 3.00, "unit": "1M tokens"},
    "Claude 3 Haiku": {"rate": 0.25, "unit": "1M tokens"},
    "Gemini 2.5 Flash Lite": {"rate": 0.10, "unit": "1M tokens"},
    "Gemini 2.5 Pro": {"rate": 1.25, "unit": "1M tokens"},
}

# LLM Gateway + LeMUR Output Tokens
llm_output_tokens = {
    "GPT 4.1": {"rate": 8.00, "unit": "1M tokens"},
    "Claude Haiku 4.5": {"rate": 5.00, "unit": "1M tokens"},
    "Claude Opus 4": {"rate": 75.00, "unit": "1M tokens"},
    "Gemini 3 Pro Preview >200k Tokens": {"rate": 18.00, "unit": "1M tokens"},
    "GPT 5 Mini": {"rate": 2.00, "unit": "1M tokens"},
    "GPT OSS 120b": {"rate": 0.60, "unit": "1M tokens"},
    "GPT 5 Nano": {"rate": 0.40, "unit": "1M tokens"},
    "GPT OSS 20b": {"rate": 0.30, "unit": "1M tokens"},
    "ChatGPT 4o Latest": {"rate": 15.00, "unit": "1M tokens"},
    "Gemini 3 Pro Preview <200k Tokens": {"rate": 12.00, "unit": "1M tokens"},
    "Claude Sonnet 4": {"rate": 15.00, "unit": "1M tokens"},
    "Claude 3.5 Haiku": {"rate": 4.00, "unit": "1M tokens"},
    "Claude 3 Haiku": {"rate": 1.25, "unit": "1M tokens"},
    "Gemini 2.5 Flash Lite": {"rate": 0.40, "unit": "1M tokens"},
    "Gemini 2.5 Flash": {"rate": 2.50, "unit": "1M tokens"},
    "Gemini 2.5 Pro": {"rate": 10.00, "unit": "1M tokens"},
}


def print_category(title, data):
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    for model, info in data.items():
        beta = " [BETA]" if info.get("beta") else ""
        print(f"{model:40} ${info['rate']:>8.2f} / {info['unit']}{beta}")


if __name__ == "__main__":
    print("\n🎯 AssemblyAI Billing Rates (US)")
    print(f"Account Balance: $58.29")
    
    print_category("Speech-to-Text", speech_to_text)
    print(f"\nNote: When Multichannel=True, billing = duration × channels × rate")
    
    print_category("Streaming Speech-to-Text", streaming_speech_to_text)
    print_category("Speech Understanding", speech_understanding)
    print_category("LLM Gateway + LeMUR - Input Tokens", llm_input_tokens)
    print_category("LLM Gateway + LeMUR - Output Tokens", llm_output_tokens)
    
    print(f"\n{'='*60}")
    print(f"Total Models: {len(speech_to_text) + len(streaming_speech_to_text) + len(speech_understanding) + len(llm_input_tokens) + len(llm_output_tokens)}")
    print(f"{'='*60}\n")
