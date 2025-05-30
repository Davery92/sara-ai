import json
import logging
import uuid
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities from the same directory
from .activities import (
    enhance_prompt_activity,
    publish_to_nats_activity,
    save_artifact_activity,
    fetch_document_content_activity
)

# Import the LLM activity from llm_proxy. This might need path adjustment in a real setup.
# For now, assuming it can be imported. If workers are separate, use fully qualified task queue names.
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

    @workflow.run
    async def run(self, config: dict) -> None:
        self._message_history = config.get("initial_messages", [])
        self._user_id = config["user_id"]
        self._room_id = config.get("room_id", self._user_id) # Default room_id to user_id if not provided
        self._nats_reply_subject = config["nats_reply_subject"]
        self_nats_ack_subject = config.get("nats_ack_subject") # Can be None
        self._nats_url = config["nats_url"]
        self._gateway_api_url = config["gateway_api_url"]
        self._session_auth_token = config["session_auth_token"]
        self._llm_model = config.get("llm_model", "default_model_name") # Ensure a default
        self._default_persona = config.get("default_persona", self._default_persona)
        self._memory_template = config.get("memory_template", self._memory_template)
        self._memory_top_n = config.get("memory_top_n", self._memory_top_n)

        self._nats_headers = {"Ack": self._nats_ack_subject} if self._nats_ack_subject else None

        log.info(
            f"Workflow started. User: {self._user_id}, Room: {self._room_id}, "
            f"ReplyTo: {self._nats_reply_subject}, LLM Model: {self._llm_model}"
        )

        # 1. Enhance initial prompt
        self._message_history = await workflow.execute_activity(
            enhance_prompt_activity,
            args=[
                self._message_history,
                self._user_id,
                self._room_id,
                self._session_auth_token,
                self._gateway_api_url,
                self._default_persona,
                self._memory_template,
                self._memory_top_n
            ],
            start_to_close_timeout=self._activity_timeout,
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # 2. Initial LLM call (with tool support enabled)
        llm_response = await workflow.execute_activity(
            call_ollama_with_tool_support, # This is from llm_proxy
            args=[self._llm_model, self._message_history, True, True],  # model, messages, stream, use_document_tools
            start_to_close_timeout=self._llm_activity_timeout,
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Main loop for processing LLM responses and tool calls
        await self._process_llm_response(llm_response)
        
        log.info(f"Workflow finished for User: {self._user_id}, Room: {self._room_id}")
        return

    async def _process_llm_response(self, llm_response: dict):
        if llm_response["type"] == "tool_calls":
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
                    doc_id = str(uuid.uuid4())
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
                    # Prompt for content generation (could be more sophisticated)
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

                    # Stream user-facing confirmation message
                    confirmation_message = f"I've created the document '{title}' (ID: {doc_id}) for you."
                    for chunk in [confirmation_message]: # Can break into chunks if needed
                         await workflow.execute_activity(
                            publish_to_nats_activity,
                            args=[self._nats_url, self._nats_reply_subject,
                                  {"type": "chat_chunk", "payload": {"delta_content": chunk}},
                                  self._nats_headers],
                            start_to_close_timeout=self._activity_timeout
                        )
                    # Signal end of chat message stream if necessary (handled by chat_finish typically)

                elif function_name == "updateDocument":
                    doc_id_to_update = function_args.get("document_id")
                    update_description = function_args.get("description")

                    if not doc_id_to_update or not update_description:
                         tool_content_for_llm = "Error: updateDocument requires both document_id and description."
                         log.warning(tool_content_for_llm)
                    else:
                        log.info(f"Fetching document {doc_id_to_update} for update.")
                        try:
                            # Fetch current document content and metadata
                            # Assumes fetch_document_content_activity returns latest document data including content, title, kind
                            document_data = await workflow.execute_activity(
                                fetch_document_content_activity,
                                args=[self._gateway_api_url, doc_id_to_update, self._session_auth_token],
                                start_to_close_timeout=self._activity_timeout,
                                retry_policy=RetryPolicy(maximum_attempts=2)
                            )

                            current_content = document_data.get("content", "")
                            doc_title = document_data.get("title", "Untitled Document") # Preserve title/kind
                            doc_kind = document_data.get("kind", "text")

                            log.info(f"Initiating update for document {doc_id_to_update}.")

                            # Publish update init message
                            await workflow.execute_activity(
                                publish_to_nats_activity,
                                args=[self._nats_url, self._nats_reply_subject,
                                      {"type": "artifact_update_init", "payload": {"document_id": doc_id_to_update, "title": doc_title, "kind": doc_kind}},
                                      self._nats_headers],
                                start_to_close_timeout=self._activity_timeout
                            )

                            # Construct prompt for updated content generation
                            update_prompt_messages = list(self._message_history) # Use current context
                            update_prompt_messages.append({
                                "role": "user",
                                "content": f"Please update the following document content based on the user's request: '{update_description}'.\n\nCurrent content:\n\n```\n{current_content}\n```\n\nProvide the full updated content."
                            })

                            # Generate updated content
                            updated_content_llm_response = await workflow.execute_activity(
                                call_ollama_with_tool_support,
                                args=[self._llm_model, update_prompt_messages, True, False], # Stream, no tools
                                start_to_close_timeout=self._llm_activity_timeout
                            )

                            full_updated_content = ""
                            if updated_content_llm_response["type"] == "chat_content":
                                for chunk in updated_content_llm_response["content"]:
                                    full_updated_content += chunk
                                    # Stream delta updates
                                    await workflow.execute_activity(
                                        publish_to_nats_activity,
                                        args=[self._nats_url, self._nats_reply_subject,
                                              {"type": "artifact_delta", "payload": {"document_id": doc_id_to_update, "delta_content": chunk}},
                                              self._nats_headers],
                                        start_to_close_timeout=self._activity_timeout
                                    )
                            else:
                                log.warning(f"Could not generate updated content for document {doc_id_to_update}. LLM response: {updated_content_llm_response}")
                                full_updated_content = current_content # Fallback to original content on error?
                                tool_content_for_llm = f"Failed to generate updated content for document {doc_id_to_update}."

                            # Publish artifact finish message
                            await workflow.execute_activity(
                                publish_to_nats_activity,
                                args=[self._nats_url, self._nats_reply_subject,
                                      {"type": "artifact_finish", "payload": {"document_id": doc_id_to_update}},
                                      self._nats_headers],
                                start_to_close_timeout=self._activity_timeout
                            )

                            if updated_content_llm_response["type"] == "chat_content":
                                # Save the new version of the document
                                await workflow.execute_activity(
                                    save_artifact_activity,
                                    args=[self._gateway_api_url, doc_id_to_update, doc_title, doc_kind, full_updated_content, self._session_auth_token],
                                    start_to_close_timeout=self._activity_timeout
                                )
                                tool_content_for_llm = f"Successfully updated document '{doc_title}' (ID: {doc_id_to_update})."

                                # Stream user-facing confirmation message
                                confirmation_message = f"I've updated the document '{doc_title}' (ID: {doc_id_to_update}) for you."
                                for chunk in [confirmation_message]: # Can break into chunks if needed
                                     await workflow.execute_activity(
                                        publish_to_nats_activity,
                                        args=[self._nats_url, self._nats_reply_subject,
                                              {"type": "chat_chunk", "payload": {"delta_content": chunk}},
                                              self._nats_headers],
                                        start_to_close_timeout=self._activity_timeout
                                    )
                                # Signal end of chat message stream if necessary (handled by chat_finish typically)

                        except Exception as e:
                            log.error(f"Error processing updateDocument for {doc_id_to_update}: {e}")
                            tool_content_for_llm = f"Failed to update document {doc_id_to_update}. Error: {e}"
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

        elif llm_response["type"] == "chat_content":
            # Stream chat content to NATS reply subject
            for chunk in llm_response["content"]:
                await workflow.execute_activity(
                    publish_to_nats_activity,
                    args=[self._nats_url, self._nats_reply_subject, 
                          {"type": "chat_chunk", "payload": {"delta_content": chunk}}, # Distinguish from artifact_delta
                          self._nats_headers],
                    start_to_close_timeout=self._activity_timeout
                )
            
            # Send a final message if needed, e.g., to signal end of stream if not done by [DONE]
            # This might include the finish_reason from the LLM if it's useful client-side.
            final_chat_payload = {"type": "chat_finish", "payload": {"finish_reason": llm_response.get("finish_reason", "stop")}}
            await workflow.execute_activity(
                publish_to_nats_activity,
                args=[self._nats_url, self._nats_reply_subject, final_chat_payload, self._nats_headers],
                start_to_close_timeout=self._activity_timeout
            )
            # Update message history with assistant's final response
            full_assistant_response = "".join(llm_response["content"])
            self._message_history.append({"role": "assistant", "content": full_assistant_response})

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

</rewritten_file> 