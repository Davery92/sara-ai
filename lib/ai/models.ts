export interface ChatModel {
  id: string;
  name: string;
  description?: string;
  // Any other relevant fields from the backend can be added here
}

// If you have a list of default/fallback models, it can be kept or removed.
// For now, let's assume the backend is the source of truth and remove predefined lists
// unless they serve a specific purpose (e.g. UI display before fetch).

// export const AVAILABLE_MODELS: Array<ChatModel> = [
//   {
//     id: 'llama3-8b-8192',
//     name: 'Llama 3 8B',
//     description: 'The Llama 3 instruction-tuned 8B model by Meta.',
//   },
//   {
//     id: 'mixtral-8x7b-32768',
//     name: 'Mixtral 8x7B',
//     description: 'The Mixtral-8x7B Large Language Model (LLM) is a pretrained generative Sparse Mixture of Experts.',
//   },
// ];

// export const DEFAULT_MODEL_ID = AVAILABLE_MODELS[0]?.id; 