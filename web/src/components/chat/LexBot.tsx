"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MessageSquare, X, Send, Sparkles, Trash2 } from "lucide-react";
import { LEX_KB as KB, type LexEntry as Entry } from "@/lib/lexbot-kb";

function cn(...classes: (string | boolean | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}

const OPEN_LEXBOT_EVENT = "dpdp-open-lexbot";
const notifyProgressUpdate = () => {};

type Msg = { who: "user" | "bot"; text: string; title?: string };

const SUGGESTIONS = [
  "What is valid consent?",
  "Penalties for a breach?",
  "Children's data rules",
  "Who must comply?",
];

function findAnswer(q: string): { title: string; answer: string } {
  const term = q.toLowerCase();
  let best: Entry | null = null;
  let bestScore = 0;
  for (const e of KB) {
    let score = 0;
    for (const k of e.keywords) if (term.includes(k)) score += k.length;
    if (score > bestScore) {
      bestScore = score;
      best = e;
    }
  }
  if (best && bestScore > 0) return { title: best.title, answer: best.answer };
  return {
    title: "Not sure yet",
    answer:
      "I couldn't find that. Try asking about consent, notice, penalties, breach, children, rights, cross-border transfers, the Board, or who must comply.",
  };
}

export function LexBot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("dpdp-lexbot-chat");
      if (raw) setMsgs(JSON.parse(raw));
    } catch {
      /* ignore */
    }
    const openBot = () => setOpen(true);
    window.addEventListener(OPEN_LEXBOT_EVENT, openBot);
    return () => window.removeEventListener(OPEN_LEXBOT_EVENT, openBot);
  }, []);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, open]);

  const persist = (next: Msg[]) => {
    setMsgs(next);
    try {
      localStorage.setItem("dpdp-lexbot-chat", JSON.stringify(next.slice(-40)));
      window.dispatchEvent(new Event("storage"));
      notifyProgressUpdate();
    } catch {
      /* ignore */
    }
  };

  const ask = (q: string) => {
    const query = q.trim();
    if (!query) return;
    const a = findAnswer(query);
    persist([
      ...msgs,
      { who: "user", text: query },
      { who: "bot", text: a.answer, title: a.title },
    ]);
    setInput("");
  };

  const clear = () => persist([]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Open LexBot assistant"
        className="fixed bottom-6 right-6 z-[55] grid h-14 w-14 place-items-center rounded-full text-[var(--on-accent)] shadow-glow transition-transform hover:scale-105"
        style={{ background: "linear-gradient(180deg, var(--color-accent-soft, #ff9a4d), var(--color-accent, #ff7a18))", color: "#1a0c00" }}
      >
        {open ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.96 }}
            transition={{ duration: 0.22 }}
            className="fixed bottom-24 right-6 z-[55] flex h-[520px] w-[min(380px,calc(100vw-3rem))] flex-col overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[#0b1019]/95 backdrop-blur-xl shadow-glow"
          >
            <div className="flex items-center justify-between border-b border-[var(--color-line)] px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--color-accent)]/15 text-[var(--color-accent)]">
                  <Sparkles className="h-4 w-4" />
                </span>
                <div>
                  <div className="text-sm font-semibold text-white">LexBot</div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
                    DPDP assistant · on-device
                  </div>
                </div>
              </div>
              {msgs.length > 0 && (
                <button
                  onClick={clear}
                  aria-label="Clear chat"
                  className="grid h-8 w-8 place-items-center rounded-full border border-[var(--color-line)] text-[var(--color-text-faint)] hover:text-white"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>

            <div ref={bodyRef} className="flex-1 space-y-3 overflow-y-auto p-4">
              {msgs.length === 0 && (
                <div className="text-sm text-[var(--color-text-muted)]">
                  <p>
                    Hi! I&apos;m <strong className="text-white">LexBot</strong>. Ask me
                    anything about the DPDP Act &amp; Rules.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => ask(s)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line)] bg-white/5 px-3 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)]/40 hover:text-white"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {msgs.map((m, i) => (
                <div
                  key={i}
                  className={cn("flex", m.who === "user" ? "justify-end" : "justify-start")}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm",
                      m.who === "user"
                        ? "bg-[var(--color-accent)]/15 text-white"
                        : "border border-[var(--color-line)] bg-[var(--color-surface-2)]/60 text-[var(--color-text-muted)]"
                    )}
                  >
                    {m.title && m.who === "bot" && (
                      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-[var(--color-accent)]">
                        {m.title}
                      </div>
                    )}
                    {m.text}
                  </div>
                </div>
              ))}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(input);
              }}
              className="flex items-center gap-2 border-t border-[var(--color-line)] p-3"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about the DPDP Act…"
                className="min-w-0 flex-1 rounded-full border border-[var(--color-line)] bg-[var(--color-surface-2)]/60 px-4 py-2.5 text-sm text-white outline-none placeholder:text-[var(--color-text-faint)] focus:border-[var(--color-accent)]/50"
              />
              <button
                type="submit"
                aria-label="Send"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-full"
                style={{ background: "linear-gradient(180deg, var(--color-accent-soft, #ff9a4d), var(--color-accent, #ff7a18))", color: "#1a0c00" }}
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
