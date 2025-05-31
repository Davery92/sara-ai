import json
import logging
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities using absolute imports
from workflows.dialogue_worker.activities import (
    enhance_prompt_activity,
    publish_to_nats_activity,
    save_artifact_activity,
    generate_chat_title_activity, # NEW
    update_chat_title_activity, # NEW
)

# Import the LLM activity from llm_proxy.
from services.llm_proxy.app.activity import call_ollama_with_tool_support

log = logging.getLogger(__name__)

@workflow.defn
class ChatOrchestrationWorkflow:
    def __init__(self):
        self._message_history: list[dict] = []
        self._user_id: str = ""
        self._room_id: str = ""
        self._nats_reply_subject: str = ""
        self._nats_ack_subject: str | None = None # Optional, for NATS headers
        self._nats_url: str = ""
        self._gateway_api_url: str = ""
        self._session_auth_token: str = ""
        self._llm_model: str = ""
        self._default_persona: str = "You are a helpful AI assistant."
        self._memory_template: str = "Previous conversation summaries:\n{memories}"
        self._memory_top_n: int = 3
        self._activity_timeout = timedelta(seconds=60)
        self._llm_activity_timeout = timedelta(seconds=180) # Longer for LLM calls
        self._is_first_interaction = True # Track if it's the first message in this chat session

    @workflow.run
    async def run(self, config: dict) -> None:
        # Initialize workflow state from config
        self._message_history = config.get("initial_messages", []) # Historical messages from client/gateway
        latest_user_msg_text = config.get("msg") # The user's typed text
        attachments_metadata = config.get("attachments", []) # List of attachment metadata dicts
        
        self._user_id = config["user_id"]
        self._room_id = config.get("room_id", self._user_id)
        self._nats_reply_subject = config["nats_reply_subject"]
        self._nats_ack_subject = config.get("nats_ack_subject")
        self._nats_url = config["nats_url"]
        self._gateway_api_url = config["gateway_api_url"]
        self._session_auth_token = config["session_auth_token"]
        self._llm_model = config.get("llm_model", "qwen3:32b") # Use a real default
        self._default_persona = config.get("default_persona", self._default_persona)
        self._memory_template = config.get("memory_template", self._memory_template)
        self._memory_top_n = config.get("memory_top_n", self._memory_top_n)
        self._is_first_interaction = (len(self._message_history) == 0) # Based on history sent by client

        # Initialize NATS headers with both Ack and Room-Id
        self._nats_headers = {}
        if self._nats_ack_subject:
            self._nats_headers["Ack"] = self._nats_ack_subject
        if self._room_id:
            self._nats_headers["Room-Id"] = str(self._room_id)  # Ensure it's a string UUID
        
        # Set to None if no headers are needed (shouldn't happen in practice)
        if not self._nats_headers:
            self._nats_headers = None

        log.info(f"Workflow run for User: {self._user_id}, Room: {self._room_id}. First interaction: {self._is_first_interaction}")

        extracted_file_content_for_prompt = "" # Initialize

        # Check if attachments already contain extracted text (from gateway upload)
        if attachments_metadata and isinstance(attachments_metadata, list) and len(attachments_metadata) > 0:
            first_attachment = attachments_metadata[0]
            
            # Check if text was already extracted during upload
            if "extracted_text" in first_attachment:
                extracted_file_content_for_prompt = first_attachment["extracted_text"]
                original_filename = first_attachment.get("original_filename", "uploaded file")
                log.info(f"Using pre-extracted text from gateway for '{original_filename}'")
                log.info(f"Pre-extracted content length: {len(extracted_file_content_for_prompt)} characters")
                log.info(f"Content preview (first 300 chars): {extracted_file_content_for_prompt[:300]}")
                if len(extracted_file_content_for_prompt) > 300:
                    log.info(f"Content preview (last 200 chars): ...{extracted_file_content_for_prompt[-200:]}")
            else:
                log.warning(f"Attachment found but no extracted_text field - file may not support text extraction")

        # 1. Enhance prompt: Pass the extracted content (from gateway or empty string)
        llm_ready_messages = await workflow.execute_activity(
            enhance_prompt_activity,
            args=[
                list(self._message_history), # Pass a copy of current history
                latest_user_msg_text,
                self._user_id,
                self._room_id,
                self._session_auth_token,
                self._gateway_api_url,
                self._default_persona,
                self._memory_template,
                self._memory_top_n,
                extracted_file_content_for_prompt, # <<< NEW ARGUMENT
                attachments_metadata # <<< NEW ARGUMENT (original metadata)
            ],
            start_to_close_timeout=self._activity_timeout,
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        # Update message history with the fully prepared messages for the LLM
        # This list now contains the system prompt, historical messages, and the latest user turn
        # (which itself includes the typed text and injected file content if any)
        self._message_history = llm_ready_messages 

        log.info(f"Enhanced prompt received from enhance_prompt_activity:")
        log.info(f"  - Total messages for LLM: {len(self._message_history)}")
        
        # Check if file content was successfully injected
        user_messages = [msg for msg in self._message_history if msg.get("role") == "user"]
        if user_messages and extracted_file_content_for_prompt:
            latest_user_msg = user_messages[-1]
            if isinstance(latest_user_msg.get("content"), list):
                file_content_found = any("uploaded a file" in str(part.get("text", "")) for part in latest_user_msg["content"])
                log.info(f"  - File content injection status: {'✅ SUCCESS' if file_content_found else '❌ FAILED'}")
                if file_content_found:
                    total_content_length = sum(len(str(part.get("text", ""))) for part in latest_user_msg["content"])
                    log.info(f"  - Total user message content length: {total_content_length} characters")

        # 2. LLM call
        # If file content was injected, we typically don't need the LLM to use tools for *this specific file extraction*.
        # However, you might still want other tools enabled (like createDocument).
        # For this specific case of answering about an uploaded file whose content is NOW in the prompt:
        use_document_tools_for_this_call = not bool(extracted_file_content_for_prompt)

        log.info(f"Calling LLM. Model: {self._llm_model}, Use Document Tools: {use_document_tools_for_this_call}")
        log.info(f"File content was {'injected' if extracted_file_content_for_prompt else 'not present'}, so document tools are {'disabled' if extracted_file_content_for_prompt else 'enabled'}")

        llm_response = await workflow.execute_activity(
            call_ollama_with_tool_support,
            args=[self._llm_model, self._message_history, True, use_document_tools_for_this_call],
            start_to_close_timeout=self._llm_activity_timeout,
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        log.info(f"LLM response received:")
        log.info(f"  - Response type: {llm_response.get('type', 'unknown')}")
        if llm_response.get("type") == "chat_content":
            content_length = sum(len(chunk) for chunk in llm_response.get("content", []))
            log.info(f"  - Chat content length: {content_length} characters")
            if content_length > 0:
                first_chunk = llm_response.get("content", [""])[0]
                log.info(f"  - Response preview: {first_chunk[:200]}...")
        elif llm_response.get("type") == "tool_calls":
            tool_calls = llm_response.get("content", [])
            log.info(f"  - Tool calls: {len(tool_calls)} tools requested")
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name", "unknown")
                log.info(f"    - Tool: {tool_name}")

        # Process LLM response (might involve further tool calls if LLM decided to use other tools)
        await self._process_llm_response(llm_response) 

        # Title generation if it was the first user-initiated message in this session
        if self._is_first_interaction and latest_user_msg_text: # Only if there was an actual user message
            first_user_message_obj = next((m for m in self._message_history if m["role"] == "user"), None)
            first_assistant_obj = next((m for m in self._message_history if m["role"] == "assistant"), None)

            if first_user_message_obj and first_user_message_obj.get("content") and \
               first_assistant_obj and first_assistant_obj.get("content"):
                
                # If user content was a list (due to file injection), join it for title generation
                user_content_for_title = first_user_message_obj["content"]
                if isinstance(user_content_for_title, list):
                    user_content_for_title = " ".join(part.get("text", "") for part in user_content_for_title if part.get("type") == "text").strip()
                
                assistant_content_for_title = first_assistant_obj["content"]
                if isinstance(assistant_content_for_title, list): # Should not happen for assistant if no tools were called by it
                     assistant_content_for_title = " ".join(part.get("text", "") for part in assistant_content_for_title if part.get("type") == "text").strip()

                log.info(f"First interaction. User: '{user_content_for_title[:100]}...', Assistant: '{str(assistant_content_for_title)[:100]}...'. Generating title.")
                
                generated_title = await workflow.execute_activity(
                    generate_chat_title_activity,
                    args=[
                        workflow.conf().llm_proxy_url,
                        self._llm_model, # Or a specific, faster model for titles
                        user_content_for_title,
                        str(assistant_content_for_title) # Ensure it's a string
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=1)
                )
                if generated_title and generated_title != "Untitled Chat":
                    await workflow.execute_activity(
                        update_chat_title_activity,
                        args=[self._gateway_api_url, self._room_id, generated_title, self._session_auth_token],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=1)
                    )
            else:
                log.warning(f"Could not generate title for chat {self._room_id}: missing first user or assistant message content in history.")

        log.info(f"Workflow finished for User: {self._user_id}, Room: {self._room_id}")
        return

    async def _process_llm_response(self, llm_response: dict):
        # This function handles LLM responses, including tool calls and chat content
        if llm_response["type"] == "chat_content":
            # Stream chat content to NATS reply subject
            full_assistant_response_text = ""
            for chunk in llm_response["content"]:
                full_assistant_response_text += chunk
                await workflow.execute_activity(
                    publish_to_nats_activity,
                    args=[self._nats_url, self._nats_reply_subject, 
                          {"type": "chat_chunk", "payload": {"delta_content": chunk}},
                          self._nats_headers],
                    start_to_close_timeout=self._activity_timeout
                )
            
            # Update internal message history with the full assistant response
            self._message_history.append({"role": "assistant", "content": full_assistant_response_text})

            final_chat_payload = {"type": "chat_finish", "payload": {"finish_reason": llm_response.get("finish_reason", "stop")}}
            await workflow.execute_activity(
                publish_to_nats_activity,
                args=[self._nats_url, self._nats_reply_subject, final_chat_payload, self._nats_headers],
                start_to_close_timeout=self._activity_timeout
            )
            
        elif llm_response["type"] == "tool_calls":
            tool_calls = llm_response["content"]
            finish_reason = llm_response["finish_reason"]

            # Add original assistant message with tool_calls to history
            self._message_history.append({"role": "assistant", "tool_calls": tool_calls})

            tool_results_for_llm = []
            for tool_call in tool_calls:
                tool_call_id = tool_call["id"]
                function_name = tool_call["function"]["name"]
                try:
                    function_args_str = tool_call["function"]["arguments"]
                    function_args = json.loads(function_args_str)
                except json.JSONDecodeError as e:
                    log.error(f"Failed to parse arguments for tool {function_name}: {function_args_str}. Error: {e}")
                    tool_results_for_llm.append({
                        "tool_call_id": tool_call_id,
                        "role": "tool",
                        "name": function_name,
                        "content": f"Error: Could not parse arguments for tool {function_name}. Input was: {function_args_str}"
                    })
                    continue # Skip to next tool call if args are bad

                log.info(f"Processing tool: {function_name} with args: {function_args}")
                tool_content_for_llm = ""

                if function_name == "createDocument":
                    doc_id = workflow.uuid4()
                    title = function_args.get("title", "Untitled Document")
                    kind = function_args.get("kind", "text")

                    await workflow.execute_activity(
                        publish_to_nats_activity,
                        args=[self._nats_url, self._nats_reply_subject, 
                              {"type": "artifact_create_init", "payload": {"document_id": doc_id, "title": title, "kind": kind}},
                              self._nats_headers],
                        start_to_close_timeout=self._activity_timeout
                    )
                    
                    # Generate content for the new document
                    content_prompt_messages = list(self._message_history) # Use current context
                    content_prompt_messages.append({
                        "role": "user", 
                        "content": f"Please generate the full content for the document titled '{title}' (kind: {kind}). Focus on providing comprehensive information based on our conversation so far."
                    })
                    
                    content_llm_response = await workflow.execute_activity(
                        call_ollama_with_tool_support,
                        args=[self._llm_model, content_prompt_messages, True, False], # No tools for content gen itself
                        start_to_close_timeout=self._llm_activity_timeout
                    )

                    full_generated_content = ""
                    if content_llm_response["type"] == "chat_content":
                        for chunk in content_llm_response["content"]:
                            full_generated_content += chunk
                            await workflow.execute_activity(
                                publish_to_nats_activity,
                                args=[self._nats_url, self._nats_reply_subject, 
                                      {"type": "artifact_delta", "payload": {"document_id": doc_id, "delta_content": chunk}},
                                      self._nats_headers],
                                start_to_close_timeout=self._activity_timeout
                            )
                    else:
                        log.warning(f"Could not generate content for document {doc_id}. LLM response: {content_llm_response}")
                        full_generated_content = "Error: Could not generate document content."
                    
                    await workflow.execute_activity(
                        publish_to_nats_activity,
                        args=[self._nats_url, self._nats_reply_subject, 
                              {"type": "artifact_finish", "payload": {"document_id": doc_id}},
                              self._nats_headers],
                        start_to_close_timeout=self._activity_timeout
                    )
                    
                    await workflow.execute_activity(
                        save_artifact_activity,
                        args=[self._gateway_api_url, doc_id, title, kind, full_generated_content, self._session_auth_token],
                        start_to_close_timeout=self._activity_timeout
                    )
                    tool_content_for_llm = f"Successfully initiated creation of document '{title}' (ID: {doc_id}). Content has been generated and streamed."

                elif function_name == "updateDocument":
                    # Similar logic for update: fetch, generate, stream, save
                    doc_id_to_update = function_args.get("document_id")
                    update_description = function_args.get("description")
                    tool_content_for_llm = f"Tool 'updateDocument' for doc ID {doc_id_to_update} with description '{update_description}' is not fully implemented in workflow yet."
                    log.warning(tool_content_for_llm)
                    
                elif function_name == "extractTextFromFile":
                    # This should rarely be called now since content is pre-injected, but handle gracefully
                    object_name_arg = function_args.get("object_name")
                    original_filename_arg = function_args.get("original_filename")
                    if object_name_arg and original_filename_arg:
                        try:
                            extracted_text = await workflow.execute_activity(
                                extract_text_from_file_activity, 
                                args=[object_name_arg, original_filename_arg],
                                start_to_close_timeout=timedelta(seconds=60) 
                            )
                            tool_content_for_llm = f"Extracted text from '{original_filename_arg}':\n{extracted_text[:1500]}..." 
                            if len(extracted_text) > 1500:
                                 tool_content_for_llm += "\n[Note: Content truncated for brevity]"
                            log.info(f"Text extraction successful for {original_filename_arg}.")
                        except Exception as e:
                            log.error(f"Error extracting text from {original_filename_arg}: {e}")
                            tool_content_for_llm = f"[Error extracting text from file '{original_filename_arg}': {str(e)}]"
                    else:
                        log.error("Missing object_name or original_filename for extractTextFromFile tool call.")
                        tool_content_for_llm = "[Error: Missing file identifier for text extraction]"
                else:
                    tool_content_for_llm = f"Unknown tool: {function_name}"
                    log.warning(tool_content_for_llm)
                
                tool_results_for_llm.append({
                    "tool_call_id": tool_call_id, 
                    "role": "tool", 
                    "name": function_name, 
                    "content": tool_content_for_llm
                })
            
            self._message_history.extend(tool_results_for_llm)
            
            # Call LLM again with tool results to get final user response
            final_llm_response = await workflow.execute_activity(
                call_ollama_with_tool_support,
                args=[self._llm_model, self._message_history, True, False], # No tools generally for final response
                start_to_close_timeout=self._llm_activity_timeout
            )
            await self._process_llm_response(final_llm_response) # Recursive call for the final response

        elif llm_response["type"] == "error":
            log.error(f"LLM call failed: {llm_response['content']}")
            await workflow.execute_activity(
                publish_to_nats_activity,
                args=[self._nats_url, self._nats_reply_subject, 
                      {"type": "error", "payload": {"message": llm_response['content']}},
                      self._nats_headers],
                start_to_close_timeout=self._activity_timeout
            )
        else:
            log.error(f"Unknown LLM response type: {llm_response.get('type')}")
            # Handle unknown type

    # TODO: Define signals for adding messages if conversation is long-running
    # @workflow.signal
    # async def add_message(self, message: dict):
    #     self._message_history.append(message)
    #     # Potentially re-trigger LLM call or other logic based on new message
