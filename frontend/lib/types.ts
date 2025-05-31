import type { Attachment as BaseAttachment } from 'ai';

// Extended attachment type that includes extracted text and metadata
export interface ExtendedAttachment extends BaseAttachment {
  extracted_text?: string;
  original_filename?: string;
  object_name?: string;
}

// Re-export the base Attachment type for compatibility
export type { BaseAttachment as Attachment };

export type DataPart = { type: 'append-message'; message: string };
