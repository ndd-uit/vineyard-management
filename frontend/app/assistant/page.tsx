"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { ChatGrapeLoader } from "@/components/ui/GrapeLoaders";
import { ApiError, apiPost } from "@/lib/api";
import type { ChatHistoryItem, ChatResponse, PendingAction } from "@/types/api";

type Message = ChatHistoryItem & { type?: ChatResponse["type"]; preview?: PendingAction; options?: { label: string; value: string }[] };

function clarificationOptions(response: ChatResponse): { label: string; value: string }[] {
  const candidates = response.options ?? (Array.isArray(response.data) ? response.data : []);
  return candidates.filter((item): item is { label: string; value: string } =>
    typeof item === "object" && item !== null && typeof item.label === "string" && typeof item.value === "string"
  );
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const busyRef = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const history = messages.slice(-12).map(({ role, message: content }) => ({ role, message: content }));
      const response = await apiPost<ChatResponse>("assistant/chat", {
        message,
        history,
        pending_action: pendingAction,
      });
      const reply: Message = {
        role: "assistant",
        message: response.message,
        type: response.type,
        preview: response.type === "ACTION_PREVIEW" ? response.pending_action ?? undefined : undefined,
        options: response.type === "CLARIFICATION" ? clarificationOptions(response) : undefined,
      };
      setMessages((current) => [...current, { role: "user", message }, reply]);
      setPendingAction(response.pending_action);
      setDraft("");
    } catch (error) {
      setError(error instanceof ApiError ? error.message : new ApiError().message);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(draft);
  }

  function edit() {
    setDraft("Sửa lại: ");
    inputRef.current?.focus();
  }

  return (
    <div className="assistant-page">
      <div className="page-heading"><span className="eyebrow">TRÒ CHUYỆN CÙNG CON</span><h1>Trợ lý AI</h1><p>Mẹ cứ nhắn như đang nói chuyện. Con sẽ hỏi lại trước khi ghi bất cứ điều gì.</p></div>
      <section className="chat-panel" aria-label="Cuộc trò chuyện">
        <div className="chat-messages" aria-live="polite" aria-relevant="additions text">
          {messages.length === 0 && (
            <div className="chat-welcome">
              <span className="welcome-symbol" aria-hidden="true">✦</span>
              <h2>Con đây, mẹ cần gì ạ?</h2>
              <p>Mẹ có thể hỏi tình hình vườn, công nợ hoặc nhờ con ghi một việc mới.</p>
              <div className="suggestions">
                {["Hôm nay vườn mình thế nào?", "Khách còn nợ bao nhiêu?"].map((example) => (
                  <button key={example} type="button" onClick={() => void send(example)} disabled={busy}>{example}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((item, index) => (
            <div key={index} className={`message-row ${item.role === "user" ? "from-user" : "from-assistant"}`}>
              <div className={`message-bubble ${item.type === "ACTION_EXECUTED" ? "message-success" : ""}`}>
                {item.role === "assistant" ? <Markdown skipHtml>{item.message}</Markdown> : item.message}
              </div>
              {item.type === "ACTION_PREVIEW" && item.preview && pendingAction?.action_token === item.preview.action_token && (
                <div className="action-card">
                  <strong>Xác nhận ghi lại</strong>
                  <p>{item.preview.summary}</p>
                  <div className="action-buttons">
                    <button type="button" className="button button-subtle" onClick={edit} disabled={busy}>Sửa lại</button>
                    <button type="button" className="button button-quiet" onClick={() => void send("không")} disabled={busy}>Không ghi</button>
                    <button type="button" className="button button-primary" onClick={() => void send("xác nhận")} disabled={busy || Boolean(draft.trim())}>Xác nhận</button>
                  </div>
                </div>
              )}
              {item.type === "CLARIFICATION" && index === messages.length - 1 && item.options && item.options.length > 0 && (
                <div className="choice-buttons">
                  {item.options.map((option) => <button key={`${option.label}-${option.value}`} type="button" onClick={() => void send(option.label)} disabled={busy}>{option.label}</button>)}
                </div>
              )}
            </div>
          ))}
          {busy && <ChatGrapeLoader />}
          <div ref={bottomRef} />
        </div>
        {error && <p className="chat-error" role="alert">{error}</p>}
        <form className="chat-form" onSubmit={submit}>
          <label htmlFor="assistant-input" className="sr-only">Nhắn cho trợ lý</label>
          <textarea
            id="assistant-input"
            ref={inputRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(draft); }
            }}
            placeholder={pendingAction ? "Mẹ muốn sửa gì? Ví dụ: Sửa lại giá thành..." : "Mẹ muốn hỏi hoặc ghi điều gì?"}
            rows={2}
            maxLength={2000}
            disabled={busy}
          />
          <button type="submit" className="button button-primary" disabled={busy || !draft.trim()}>Gửi</button>
        </form>
      </section>
    </div>
  );
}
