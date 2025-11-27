#!/usr/bin/env python3
"""
Compare billing rates from different sources to identify inconsistencies
"""

import json

# Load the structured data
with open('tests/billing_rates_structured.json', 'r') as f:
    web_data = json.load(f)

print("🔍 Analysis of AssemblyAI Billing Data\n")
print("="*70)

# Analyze Speech-to-Text
print("\n📊 SPEECH-TO-TEXT MODELS")
print("-"*70)
stt_models = web_data['categories']['speech_to_text']['models']
print(f"Count: {len(stt_models)} models")
for model in stt_models:
    beta_tag = " [BETA]" if model.get('beta') else ""
    print(f"  • {model['name']:20} ${model['rate']:.2f}/{model['unit']}{beta_tag}")

# Analyze Streaming
print("\n📊 STREAMING SPEECH-TO-TEXT MODELS")
print("-"*70)
streaming_models = web_data['categories']['streaming_speech_to_text']['models']
print(f"Count: {len(streaming_models)} models")
for model in streaming_models:
    print(f"  • {model['name']:30} ${model['rate']:.2f}/{model['unit']}")

# Analyze Speech Understanding
print("\n📊 SPEECH UNDERSTANDING FEATURES")
print("-"*70)
understanding_models = web_data['categories']['speech_understanding']['models']
print(f"Count: {len(understanding_models)} features")
for model in understanding_models:
    print(f"  • {model['name']:30} ${model['rate']:.2f}/{model['unit']}")

# Analyze LLM Gateway
print("\n📊 LLM GATEWAY + LEMUR")
print("-"*70)
input_models = web_data['categories']['llm_gateway_input']['models']
output_models = web_data['categories']['llm_gateway_output']['models']
print(f"Input models: {len(input_models)}")
print(f"Output models: {len(output_models)}")

# Find models that appear in both input and output
input_names = {m['name'] for m in input_models}
output_names = {m['name'] for m in output_models}

common_models = input_names & output_names
print(f"\nModels with both input/output pricing: {len(common_models)}")

# Create a comparison table
print("\n" + "="*70)
print("LLM MODEL PRICING COMPARISON (Input vs Output)")
print("="*70)
print(f"{'Model':<40} {'Input':<15} {'Output':<15}")
print("-"*70)

for model_name in sorted(common_models):
    input_rate = next((m['rate'] for m in input_models if m['name'] == model_name), None)
    output_rate = next((m['rate'] for m in output_models if m['name'] == model_name), None)
    
    if input_rate and output_rate:
        ratio = output_rate / input_rate if input_rate > 0 else 0
        print(f"{model_name:<40} ${input_rate:>6.2f}      ${output_rate:>6.2f}  ({ratio:.1f}x)")

# Models only in input
input_only = input_names - output_names
if input_only:
    print(f"\n⚠️  Models ONLY in Input pricing: {len(input_only)}")
    for name in sorted(input_only):
        rate = next(m['rate'] for m in input_models if m['name'] == name)
        print(f"  • {name}: ${rate:.2f}")

# Models only in output
output_only = output_names - input_names
if output_only:
    print(f"\n⚠️  Models ONLY in Output pricing: {len(output_only)}")
    for name in sorted(output_only):
        rate = next(m['rate'] for m in output_models if m['name'] == name)
        print(f"  • {name}: ${rate:.2f}")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"Total unique models across all categories: {web_data['summary']['total_models']}")
print(f"Speech-to-Text: {web_data['summary']['speech_to_text_count']}")
print(f"Streaming: {web_data['summary']['streaming_count']}")
print(f"Speech Understanding: {web_data['summary']['speech_understanding_count']}")
print(f"LLM Input: {web_data['summary']['llm_input_count']}")
print(f"LLM Output: {web_data['summary']['llm_output_count']}")
print(f"\nAccount Balance: ${web_data['account_balance']:.2f}")
print("="*70)

# Key observations
print("\n💡 KEY OBSERVATIONS:")
print("-"*70)
print("1. Speech-to-Text has 3 models (Slam-1 is in Beta)")
print("2. Streaming has 3 models (including legacy)")
print("3. Speech Understanding has 12 features")
print("4. LLM Gateway has separate input/output pricing")
print("5. Output tokens are typically 4-8x more expensive than input")
print("\n⚠️  POTENTIAL ISSUES TO CHECK:")
print("-"*70)
print("• Are you merging input/output rates incorrectly?")
print("• Are model counts matching between API and UI?")
print("• Are beta models being filtered out?")
print("• Is the 'unit' field being handled correctly (hour vs 1M tokens)?")
