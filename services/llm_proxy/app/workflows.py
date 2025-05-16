import asyncio
import json
import logging
import uuid
from typing import List, Dict, Any, Optional

from temporalio import workflow
from datetime import timedelta
from temporalio.common import RetryPolicy

# Import activities directly - this is compatible with older Temporalio versions
from .activity import call_ollama, call_ollama_with_tool_support, extract_artifact_details

log = logging.getLogger("llm_proxy.workflow")

@workflow.defn(name="LLMWorkflow")
class ChatWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> List[str]:
        model = payload.get("model", "default")
        prompt = payload.get("msg") or payload.get("prompt", "")
        stream = payload.get("stream", False)

        return await workflow.execute_activity(
            call_ollama,
            args=[model, prompt, stream],
            start_to_close_timeout=timedelta(minutes=2),
        )

@workflow.defn
class ChatOrchestrationWorkflow:
    """
    Orchestrates the entire process of:
    1. Detecting intent to create/update artifact via tool calls
    2. Generating the artifact content
    3. Streaming updates via WebSocket
    4. Saving the final artifact to the database
    """
    
    @workflow.run
    async def run(
        self, 
        model: str, 
        messages: list, 
        user_id: str,
        room_id: str,
        websocket_id: str
    ) -> Dict[str, Any]:
        # First, call Ollama with tool support to detect if document creation is requested
        llm_response = await workflow.execute_activity(
            call_ollama_with_tool_support,
            args=[model, messages, True, True],  # model, messages, stream, use_document_tools
            start_to_close_timeout=timedelta(minutes=3),
        )
        
        # If no tool calls detected, just return the raw chat response
        if llm_response["type"] != "tool_calls":
            return {
                "type": "chat_completion",
                "content": llm_response["content"],
                "status": "completed"
            }
        
        # Extract artifact details from tool calls
        artifact_details = await workflow.execute_activity(
            extract_artifact_details,
            args=[llm_response["content"]],
            start_to_close_timeout=timedelta(seconds=10),
        )
        
        if artifact_details["action"] == "none":
            # Tool was called but wasn't for document creation/update
            return {
                "type": "chat_completion",
                "content": ["Sorry, I couldn't process that document operation."],
                "status": "completed"
            }
            
        # Generate document_id for new documents
        document_id = str(uuid.uuid4())
        if artifact_details["action"] == "update" and "document_id" in artifact_details:
            document_id = artifact_details["document_id"]
            
        # Send WebSocket message to initialize artifact creation/update
        ws_init_message = {
            "type": f"artifact_{artifact_details['action']}_init",
            "payload": {
                "documentId": document_id,
                "title": artifact_details.get("title", "Untitled"),
                "kind": artifact_details.get("kind", "text"),
            }
        }
        
        # Call activity to send WebSocket message (to be implemented)
        # await workflow.execute_activity(
        #     send_websocket_message,
        #     args=[websocket_id, ws_init_message],
        #     start_to_close_timeout=timedelta(seconds=10),
        # )
        
        # For update operations, we'd need to fetch the current content
        current_content = ""
        if artifact_details["action"] == "update":
            # Code to fetch current document content would go here
            pass
            
        # Prepare context for content generation
        content_gen_prompt = self._build_content_generation_prompt(artifact_details, current_content, messages)
        
        # Generate the actual content
        content_gen_response = await workflow.execute_activity(
            call_ollama_with_tool_support,
            args=[model, content_gen_prompt, True, False],  # model, messages, stream, use_document_tools
            start_to_close_timeout=timedelta(minutes=5),  # Longer timeout for content generation
        )
        
        # Stream content delta updates via WebSocket
        if content_gen_response["type"] == "chat_content":
            for chunk in content_gen_response["content"]:
                ws_delta_message = {
                    "type": "artifact_delta",
                    "payload": {
                        "documentId": document_id,
                        "kind": artifact_details.get("kind", "text"),
                        "delta": chunk
                    }
                }
                # await workflow.execute_activity(
                #     send_websocket_message,
                #     args=[websocket_id, ws_delta_message],
                #     start_to_close_timeout=timedelta(seconds=10),
                # )
                
        # Save the completed document to the database
        final_content = "".join(content_gen_response["content"]) if content_gen_response["type"] == "chat_content" else ""
        
        # Create or update the document in the database
        document_data = {
            "document_id": document_id,
            "user_id": user_id,
            "room_id": room_id,
            "title": artifact_details.get("title", "Untitled"),
            "kind": artifact_details.get("kind", "text"),
            "content": final_content,
        }
        
        # Call activity to save document (to be implemented)
        # await workflow.execute_activity(
        #     save_document,
        #     args=[document_data],
        #     start_to_close_timeout=timedelta(seconds=10),
        # )
        
        # Send WebSocket message to signal completion
        ws_finish_message = {
            "type": "artifact_finish",
            "payload": {
                "documentId": document_id
            }
        }
        
        # await workflow.execute_activity(
        #     send_websocket_message,
        #     args=[websocket_id, ws_finish_message],
        #     start_to_close_timeout=timedelta(seconds=10),
        # )
        
        return {
            "type": "artifact_created",
            "document_id": document_id,
            "kind": artifact_details.get("kind", "text"),
            "title": artifact_details.get("title", "Untitled"),
            "status": "completed"
        }
    
    def _build_content_generation_prompt(self, artifact_details, current_content, messages):
        """Build a prompt for content generation based on artifact details and chat context"""
        if artifact_details["action"] == "create":
            system_prompt = f"You are creating a {artifact_details.get('kind', 'text')} document titled '{artifact_details.get('title', 'Untitled')}'. Generate appropriate content based on the conversation context."
        else:  # update
            system_prompt = f"You are updating a document based on this description: '{artifact_details.get('description', '')}'. Here is the current content:\n\n{current_content}\n\nGenerate the updated content."
            
        return [
            {"role": "system", "content": system_prompt},
            # Include recent conversation messages for context
            *messages[-5:],  # Last 5 messages for context
            {"role": "user", "content": f"Please generate the {'new' if artifact_details['action'] == 'create' else 'updated'} content for the document."}
        ]



