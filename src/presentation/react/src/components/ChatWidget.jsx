import { useEffect, useState, useRef } from 'react';
import { fetchJSON } from '../api';
import { AiOutlineArrowRight } from 'react-icons/ai';

export default function ChatWidget({ conversationId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    // Add user message
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const payload = {
        question: text,
        conversation_id: conversationId,
        top_k: 5,
      };
      const data = await fetchJSON('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const botMsg = {
        role: 'assistant',
        content: data.answer || data.content || 'No response',
        sources: data.sources || [],
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex-1 overflow-y-auto py-4">
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user';
          return (
            <div key={idx} className={`flex ${!isUser ? 'justify-start' : 'justify-end'} mb-2`}>
              <div className={`max-w-[80%] px-4 py-2 rounded-lg ${
                isUser ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-900'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {!isUser && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 text-xs text-gray-600">
                    Sources: {msg.sources.map((s, i) => (
                      <span key={i} className="mr-2">{typeof s === 'string' ? s : s.title || ''}</span>
                    ))}</div>
                )}
              </div>
            </div>
          );
        })}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center space-x-2">
              <div className="h-3 w-3 rounded-full animate-pulse bg-blue-500"></div>
              <span>Thinking…</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2 p-4 bg-white border-t">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask a question about your documents…"
          className="flex-1 px-3 py-2 border rounded disabled:opacity-50"
          disabled={loading}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), sendMessage())}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center"
        >
          <AiOutlineArrowRight className="ml-1" />
          <span>{loading ? 'Sending…' : 'Send'}</span>
        </button>
      </div>
    </div>
  );
}