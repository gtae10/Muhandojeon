import { useState, useRef, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { sendChatMessage } from '../api/client.js'
import ChatBubble from '../components/ChatBubble.jsx'

export default function ChatScreen() {
  const { productId } = useParams()
  const [messages, setMessages] = useState([
    // TODO(AI2 담당): 첫 인사 메시지를 백엔드에서 내려줄지, 프론트 고정 문구로 둘지 확정
    { role: 'agent', text: '오늘 보신 제품에 대해 궁금하신 점 있으신가요?' },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return

    setMessages((prev) => [...prev, { role: 'user', text }])
    setInput('')
    setSending(true)

    try {
      // TODO(AI2 담당): 스트리밍으로 확정되면 여기를 청크 단위 append로 교체
      const { reply } = await sendChatMessage(productId, text)
      setMessages((prev) => [...prev, { role: 'agent', text: reply }])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'agent', text: '응답을 받지 못했어요. 다시 시도해주세요.' },
      ])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-140px)]">
      <div className="flex-1 overflow-y-auto space-y-3 pb-4">
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} text={m.text} />
        ))}
        {sending && <ChatBubble role="agent" text="…" />}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2 pt-3 border-t border-white/10">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="메시지를 입력하세요"
          className="flex-1 bg-[var(--color-surface)] rounded-full px-4 py-2 text-sm outline-none"
        />
        <button
          onClick={handleSend}
          disabled={sending}
          className="px-4 py-2 rounded-full bg-[var(--color-accent)] text-black text-sm disabled:opacity-50"
        >
          전송
        </button>
      </div>
    </div>
  )
}
