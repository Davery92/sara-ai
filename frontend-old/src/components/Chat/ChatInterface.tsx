import React, { useState, useEffect, useRef } from 'react';
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

const ChatInterface: React.FC = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const [tokenError, setTokenError] = useState<boolean>(false);
  const [personas, setPersonas] = useState<string[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string>('');
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const roomId = 'default-room';

  // Theme init
  useEffect(() => {
    const saved = localStorage.getItem('darkMode') === 'true';
    setDarkMode(saved);
    document.body.classList.toggle('dark-mode', saved);
  }, []);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load personas
  useEffect(() => {
    const load = async () => {
      try {
        const list = await chatService.getPersonas();
        setPersonas(list);
        if (list.length && !selectedPersona) {
          setSelectedPersona(list[0]);
        }
      } catch (err) {
        console.error('Failed to load personas:', err);
      }
    };
    if (user) load();
  }, [user, selectedPersona]);

  const toggleDarkMode = () => {
    const next = !darkMode;
    setDarkMode(next);
    localStorage.setItem('darkMode', String(next));
    document.body.classList.toggle('dark-mode', next);
  };

  const handlePersonaChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const persona = e.target.value;
    setSelectedPersona(persona);
    try {
      await chatService.setPersona(persona);
      setMessages(prev => [
        ...prev,
        {
          id: `${Date.now()}-system`,
          content: `Persona changed to ${persona}`,
          isUser: false,
          timestamp: new Date(),
        }
      ]);
    } catch (err) {
      console.error('Error setting persona:', err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log("[ChatInterface] handleSendMessage triggered");

    if (!inputValue.trim() || isLoading) {
      console.log("[ChatInterface] handleSendMessage: Input empty or already loading, returning.");
      return;
    }

    const userContent = inputValue.trim();
    const userMsg: Message = {
      id: `${Date.now()}-user`,
      content: userContent,
      isUser: true,
      timestamp: new Date(),
    };
    console.log("[ChatInterface] User message object created:", userMsg);

    // append user message
    console.log("[ChatInterface] About to add user message to state.");
    setMessages(prev => {
      const newMessages = [...prev, userMsg];
      console.log("[ChatInterface] Adding user message. Prev messages:", prev, "New messages:", newMessages);
      return newMessages;
    });
    setInputValue('');
    setIsLoading(true);
    setTokenError(false);

    // prepare AI bubble
    const aiMsgId = `${Date.now()}-ai`;
    console.log("[ChatInterface] About to add AI placeholder message to state. AI Message ID:", aiMsgId);
    setMessages(prev => {
      const newMessages = [...prev, { id: aiMsgId, content: '', isUser: false, timestamp: new Date() }];
      console.log("[ChatInterface] Adding AI placeholder. Prev messages:", prev, "New messages:", newMessages);
      return newMessages;
    });

    try {
      console.log("[ChatInterface] Calling chatService.sendMessage with content:", userContent);
      await chatService.sendMessage(
        [{ role: 'user', content: userContent }],
        (chunk: string) => {
          console.log("[ChatInterface] chatService.sendMessage - onChunk received:", chunk);
          setMessages(prev =>
            prev.map(m =>
              m.id === aiMsgId
                ? { ...m, content: m.content + chunk }
                : m
            )
          );
        },
        (err: string) => {
          console.error('[ChatInterface] chatService.sendMessage - onError:', err);
          setTokenError(true);
        },
        roomId
      );
      console.log("[ChatInterface] chatService.sendMessage completed successfully.");
    } catch (err) {
      console.error('[ChatInterface] chatService.sendMessage - catch error:', err);
      setTokenError(true);
    } finally {
      console.log("[ChatInterface] handleSendMessage - finally block. Setting isLoading to false.");
      setIsLoading(false);
      // put focus back in the input so user can click/type immediately
      inputRef.current?.focus();
    }
  };

  return (
    <div className={`chat-interface ${darkMode ? 'dark-mode' : ''}`}>
      <div className="chat-header">
        <h2>Chat with AI</h2>
        <div className="chat-controls">
          {user && <div className="user-info">Logged in as: {user.username}</div>}
          {personas.length > 0 && (
            <div className="persona-selector">
              <label htmlFor="persona-select">Personality:</label>
              <select
                id="persona-select"
                value={selectedPersona}
                onChange={handlePersonaChange}
                disabled={isLoading}
              >
                {personas.map(p => (
                  <option key={p} value={p}>
                    {p.replace('sara_', '')}
                  </option>
                ))}
              </select>
            </div>
          )}
          <button className="theme-toggle" onClick={toggleDarkMode} aria-label="Toggle theme">
            {darkMode ? '☀️' : '🌙'}
          </button>
        </div>
      </div>

      {tokenError && <TokenRefresher />}

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="empty-chat"><p>👋 Start a conversation</p></div>
        ) : (
          messages.map(msg => (
            <ChatMessage
              key={msg.id}
              content={msg.content}
              isUser={msg.isUser}
              timestamp={msg.timestamp}
            />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-container" onSubmit={handleSendMessage}>
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
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
