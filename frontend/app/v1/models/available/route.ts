import { NextRequest, NextResponse } from 'next/server';

/**
 * API route that returns a list of available models from Ollama
 */
export async function GET(request: NextRequest) {
  try {
    // Use the Ollama API to get available models
    const ollamaUrl = process.env.LLM_BASE_URL || process.env.NEXT_PUBLIC_OLLAMA_BASE_URL || 'http://100.104.68.115:11434';
    console.log(`Attempting to fetch Ollama models from: ${ollamaUrl}`); // Added for debugging
    
    // Add a timeout to the fetch request to avoid long waits
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout
    
    try {
      const response = await fetch(`${ollamaUrl}/api/tags`, {
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      
      // Transform the Ollama response to our expected format
      const models = data.models.map((model: any) => ({
        id: model.name,
        name: model.name.replace(/-/g, ' ').replace(/(\w)(\w*)/g, (_: string, first: string, rest: string) => first.toUpperCase() + rest),
        description: `${model.size ? Math.round(model.size / (1024 * 1024 * 1024)) + 'GB' : ''} ${model.modified ? 'Updated ' + new Date(model.modified).toLocaleDateString() : ''}`.trim()
      }));
      
      return NextResponse.json({ models });
    } catch (fetchError: unknown) {
      console.error('Error fetching from Ollama API:', fetchError);
      throw new Error(`Ollama API unavailable: ${fetchError instanceof Error ? fetchError.message : 'Connection failed'}`);
    }
  } catch (error) {
    console.error('Error fetching models from Ollama:', error);
    
    // Return carefully selected fallback models that are likely to be available to the user
    return NextResponse.json({
      models: [
        {
          id: 'qwen3:32b',
          name: 'Qwen 3 32B',
          description: 'Versatile multilingual model by Alibaba with strong reasoning abilities'
        },
        {
          id: 'llama3:8b-instruct',
          name: 'Llama 3 8B Instruct',
          description: 'Optimized instruction model - smaller size, great performance'
        },
        {
          id: 'codellama:7b-instruct',
          name: 'CodeLlama 7B Instruct',
          description: 'Specialized for coding tasks with excellent instruction following'
        },
        {
          id: 'mistral:7b-instruct',
          name: 'Mistral 7B Instruct',
          description: 'High performance small model with excellent instruction following'
        },
        {
          id: 'neural-chat:7b',
          name: 'Neural Chat 7B',
          description: 'Conversational AI model with strong dialog capabilities'
        }
      ]
    });
  }
} 