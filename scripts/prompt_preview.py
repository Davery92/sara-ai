#!/usr/bin/env python3
"""
Prompt Preview Tool

A developer utility to preview how system prompts look with different personas,
memories, and user messages.

Usage:
  python prompt_preview.py --persona sara_default --memories 3 --user-message "Tell me about yourself"
  python prompt_preview.py --persona sara_formal --diff
"""

import argparse
import asyncio
import difflib
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the project root to the Python path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Now we can import our modules
from services.common.persona_service import PersonaService
MEMORY_TEMPLATE = os.getenv("MEMORY_TEMPLATE", "Previous conversation summaries:\n{memories}")


def format_colored_diff(diff_lines):
    """Format diff lines with ANSI color codes."""
    colored_lines = []
    for line in diff_lines:
        if line.startswith('+'):
            colored_lines.append(f"\033[92m{line}\033[0m")  # Green for additions
        elif line.startswith('-'):
            colored_lines.append(f"\033[91m{line}\033[0m")  # Red for removals
        elif line.startswith('^'):
            colored_lines.append(f"\033[94m{line}\033[0m")  # Blue for markers
        else:
            colored_lines.append(line)
    return '\n'.join(colored_lines)


def generate_sample_memories(count: int) -> List[str]:
    """Generate sample memories for preview purposes."""
    sample_memories = [
        "User asked about workflow optimization for their team.",
        "User mentioned they work in a healthcare setting with patient data.",
        "User prefers detailed explanations with examples.",
        "User is interested in AI ethics and governance.",
        "User has a technical background in software development.",
    ]
    return sample_memories[:count] if count <= len(sample_memories) else sample_memories


def build_prompt(persona_content: str, memories: List[str], user_message: str) -> str:
    """Build a system prompt with the provided components."""
    system_prompt = persona_content
    
    # Add memories if provided
    if memories:
        memory_text = "\n\n".join([f"- {memory}" for memory in memories])
        system_prompt = f"{system_prompt}\n\n{MEMORY_TEMPLATE.format(memories=memory_text)}"
    
    # Add user message if provided
    if user_message:
        system_prompt = f"{system_prompt}\n\nUser: {user_message}"
    
    return system_prompt


def main():
    parser = argparse.ArgumentParser(description="Preview system prompts with different personas and memories")
    parser.add_argument("--persona", dest="persona", default="sara_default",
                        help="Name of the persona to use (default: sara_default)")
    parser.add_argument("--compare-to", dest="compare_persona",
                        help="Compare with another persona")
    parser.add_argument("--memories", dest="memories", type=int, default=0,
                        help="Number of sample memories to include (0-5)")
    parser.add_argument("--user-message", dest="user_message", default="",
                        help="Sample user message to include")
    parser.add_argument("--diff", dest="show_diff", action="store_true",
                        help="Show diff when comparing personas")
    args = parser.parse_args()
    
    # Initialize the persona service
    persona_service = PersonaService()
    
    # Generate sample memories
    memories = generate_sample_memories(args.memories)
    
    # Get persona content
    try:
        persona_content = persona_service.get_persona_content(args.persona)
        if not persona_content:
            print(f"Error: Persona '{args.persona}' not found")
            return 1
    except Exception as e:
        print(f"Error loading persona: {e}")
        return 1
    
    # Build the prompt
    prompt = build_prompt(persona_content, memories, args.user_message)
    
    # Print the preview
    print("\n" + "=" * 80)
    print(f"PROMPT PREVIEW: {args.persona}")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    
    # Compare with another persona if requested
    if args.compare_persona:
        try:
            compare_content = persona_service.get_persona_content(args.compare_persona)
            if not compare_content:
                print(f"Error: Comparison persona '{args.compare_persona}' not found")
                return 1
                
            compare_prompt = build_prompt(compare_content, memories, args.user_message)
            
            if args.show_diff:
                # Generate and display the diff
                diff = difflib.unified_diff(
                    prompt.splitlines(),
                    compare_prompt.splitlines(),
                    fromfile=args.persona,
                    tofile=args.compare_persona,
                    lineterm="",
                )
                print("\nDIFF:")
                print(format_colored_diff(diff))
            else:
                # Just show the second prompt
                print("\n" + "=" * 80)
                print(f"COMPARISON PROMPT: {args.compare_persona}")
                print("=" * 80)
                print(compare_prompt)
                print("=" * 80)
        except Exception as e:
            print(f"Error comparing personas: {e}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 