import React, { useState, useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import { chatService } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import TokenRefresher from '../Auth/TokenRefresher';
import './ChatInterface.css';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}

// Define type for axios error
interface ApiError {
  response?: {
    status: number;
    data?: any;
  };
  message?: string;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [tokenError, setTokenError] = useState<boolean>(false);
  const [personas, setPersonas] = useState<string[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string>('');
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user, token } = useAuth();
  const currentAiMessageRef = useRef<Message | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const roomId = 'default-room'; // You might want to make this dynamic
  const ackCounter = useRef(0);

  // Debug: Log message state when it changes
  useEffect(() => {
    console.log('Current messages:', messages);
  }, [messages]);

  // Initialize dark mode from localStorage
  useEffect(() => {
    const savedDarkMode = localStorage.getItem('darkMode') === 'true';
    setDarkMode(savedDarkMode);
    
    // Apply dark mode class to body
    if (savedDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load available personas
  useEffect(() => {
    const loadPersonas = async () => {
      try {
        const personaList = await chatService.getPersonas();
        setPersonas(personaList);
        
        // Default to first persona if available
        if (personaList.length > 0 && !selectedPersona) {
          setSelectedPersona(personaList[0]);
        }
      } catch (error) {
        console.error('Failed to load personas:', error);
      }
    };
    
    if (user) {
      loadPersonas();
    }
  }, [user]);

  // Initialize WebSocket connection
  useEffect(() => {
    const connectWebSocket = () => {
      const ws = new WebSocket(`ws://localhost:8000/v1/stream?token=${token}`);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.choices && data.choices[0]) {
            const choice = data.choices[0];
            if (choice.delta && choice.delta.content) {
              // Update the last AI message with new content
              setMessages(prevMessages => {
                const lastMessage = prevMessages[prevMessages.length - 1];
                if (lastMessage && !lastMessage.isUser) {
                  return prevMessages.map((msg, idx) => 
                    idx === prevMessages.length - 1 
                      ? { ...msg, content: msg.content + choice.delta.content }
                      : msg
                  );
                }
                return prevMessages;
              });

              // Send ACK every 10 chunks
              ackCounter.current++;
              if (ackCounter.current % 10 === 0) {
                ws.send('+ACK');
              }
            }
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Attempt to reconnect after a delay
        setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current = ws;
    };

    if (token) {
      connectWebSocket();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [token]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const toggleDarkMode = () => {
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    localStorage.setItem('darkMode', newDarkMode.toString());
    
    // Apply/remove the dark-mode class from the body
    if (newDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  };
  
  const handlePersonaChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const persona = event.target.value;
    setSelectedPersona(persona);
    
    try {
      await chatService.setPersona(persona);
      
      // Add a system message to inform user
      const systemMessage: Message = {
        id: Date.now().toString() + '-system',
        content: `Persona changed to ${persona}`,
        isUser: false,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, systemMessage]);
    } catch (error) {
      console.error('Error setting persona:', error);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputValue.trim() || isLoading) return;
    
    const userMsgId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}-user`;
    const userMessage: Message = {
      id: userMsgId,
      content: inputValue.trim(),
      isUser: true,
      timestamp: new Date(),
    };
    
    // Add user message
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setTokenError(false);
    
    try {
      // 1. First, enqueue the message via REST
      await chatService.sendMessage(userMessage.content);
      
      // 2. Then send the message through WebSocket for streaming
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        const aiMsgId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}-ai`;
        const aiMessage: Message = {
          id: aiMsgId,
          content: '',
          isUser: false,
          timestamp: new Date(),
        };
        
        setMessages(prevMessages => [...prevMessages, aiMessage]);
        
        wsRef.current.send(JSON.stringify({
          model: 'qwen3:32b',
          messages: [{ role: 'user', content: userMessage.content }],
          stream: true,
          room_id: roomId
        }));
      } else {
        throw new Error('WebSocket not connected');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      setTokenError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTokenRefreshed = () => {
    setTokenError(false);
  };

  return (
    <div className={`chat-interface ${darkMode ? 'dark-mode' : ''}`}>
      <div className="chat-header">
        <h2>Chat with AI</h2>
        <div className="chat-controls">
          {user && <div className="user-info">Logged in as: {user.username}</div>}
          
          {personas.length > 0 && (
            <div className="persona-selector">
              <label htmlFor="persona-select">Personality: </label>
              <select 
                id="persona-select"
                value={selectedPersona}
                onChange={handlePersonaChange}
                disabled={isLoading}
              >
                {personas.map((persona) => (
                  <option key={persona} value={persona}>
                    {persona.replace('sara_', '')}
                  </option>
                ))}
              </select>
            </div>
          )}
          
          <button 
            className="theme-toggle" 
            onClick={toggleDarkMode}
            aria-label="Toggle dark mode"
          >
            {darkMode ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
      
      {tokenError && (
        <TokenRefresher />
      )}
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="empty-chat">
            <p>👋 Start a conversation by sending a message</p>
          </div>
        ) : (
          messages.map(message => (
            <ChatMessage
              key={message.id}
              content={message.content}
              isUser={message.isUser}
              timestamp={message.timestamp}
            />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form className="chat-input-container" onSubmit={handleSendMessage}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Type a message..."
          disabled={isLoading}
          className="chat-input"
        />
        <button 
          type="submit" 
          disabled={isLoading || !inputValue.trim()}
          className="send-button"
        >
          {isLoading ? '...' : 'Send'}
        </button>
      </form>
    </div>
  );
};

export default ChatInterface; 