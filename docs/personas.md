# Persona Authoring Guide

This guide explains how to create and customize personas for the Sara AI assistant. Personas define the tone, style, and behavior of the assistant's responses.

## What is a Persona?

A persona defines the "personality" of Sara when interacting with users. It includes:

- **Voice & Tone**: How Sara expresses herself (formal vs. casual, technical vs. simple, etc.)
- **Interaction Style**: How Sara structures responses and engages with the user
- **Guardrails**: Boundaries and limitations that should be respected

## File Structure

Personas are defined as Markdown files in the `configs/personalities/` directory. Each file should be named according to the persona, e.g., `sara_default.md` or `sara_formal.md`.

## Creating a New Persona

1. Create a new Markdown file in `configs/personalities/` named `sara_[persona_name].md`
2. Follow the structure below to define the persona

### Required Structure

```markdown
# Sara - [Persona Name]

You are Sara, an AI assistant with [brief persona description].

## Voice & Tone
- [Guideline 1]
- [Guideline 2]
- [Guideline 3]

## Interaction Style
- [Guideline 1]
- [Guideline 2]
- [Guideline 3]

## Guardrails
- [Guideline 1]
- [Guideline 2]
- [Guideline 3]
```

### Example: Casual Persona

```markdown
# Sara - Casual

You are Sara, an AI assistant with a friendly and relaxed demeanor.

## Voice & Tone
- Use casual, conversational language
- Use contractions freely (I'll, you're, can't)
- Incorporate occasional humor when appropriate
- Be warm and enthusiastic

## Interaction Style
- Start with a warm greeting
- Use simple, accessible language
- Provide practical examples
- Ask follow-up questions to clarify

## Guardrails
- Maintain professionalism despite casual tone
- Avoid overly informal slang or internet speak
- Still provide accurate, reliable information
- Don't sacrifice clarity for friendliness
```

## Testing Your Persona

You can preview how your persona will affect the system prompt using the `prompt_preview.py` script:

```bash
python scripts/prompt_preview.py --persona sara_casual --user-message "Tell me about AI"
```

To compare with another persona:

```bash
python scripts/prompt_preview.py --persona sara_casual --compare-to sara_formal --diff
```

## Best Practices

1. **Be Specific**: Provide clear guidelines about language use, tone, and structure
2. **Include Examples**: Where helpful, include examples of phrases or responses that fit the persona
3. **Focus on Differentiators**: Emphasize what makes this persona distinct from others
4. **Consider User Needs**: Design personas with specific use cases or user preferences in mind
5. **Test Thoroughly**: Use the preview tool to check how the persona affects responses

## Integrating the Persona

Once defined, you can set a persona as the default by setting the `DEFAULT_PERSONA` environment variable to the persona name (without the `.md` extension).

Users can select their preferred persona through the API:

```http
PATCH /v1/persona
Content-Type: application/json
Authorization: Bearer <token>

{
  "persona": "sara_formal"
}
```

## Understanding How Personas Work

When the dialogue worker receives a request, it:

1. Checks if the user has a preferred persona
2. If not, uses the default persona
3. Loads the persona content and uses it as the base for the system prompt
4. Adds memories and other dynamic content to the prompt
5. Sends the enhanced prompt to the LLM

The persona serves as the foundation for how Sara responds, with memories and other context layered on top. 