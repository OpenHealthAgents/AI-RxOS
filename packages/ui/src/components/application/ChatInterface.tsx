import * as React from "react"
import { Send, User, Bot, Paperclip } from "lucide-react"
import { Button } from "../ui/button"
import { Input } from "../ui/input"
import { ScrollArea } from "../ui/scroll-area"
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar"

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp?: string
}

export interface ChatInterfaceProps {
  messages: Message[]
  onSendMessage: (content: string) => void
  isLoading?: boolean
}

export function ChatInterface({ messages, onSendMessage, isLoading }: ChatInterfaceProps) {
  const [input, setInput] = React.useState("")
  const scrollRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim())
      setInput("")
    }
  }

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden bg-card">
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <div className="flex flex-col gap-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
            >
              <Avatar className="h-8 w-8 shrink-0">
                {msg.role === "user" ? (
                  <AvatarFallback className="bg-primary/20"><User className="h-4 w-4" /></AvatarFallback>
                ) : (
                  <AvatarFallback className="bg-secondary"><Bot className="h-4 w-4" /></AvatarFallback>
                )}
              </Avatar>
              <div
                className={`rounded-lg px-4 py-2 max-w-[80%] ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex gap-3 flex-row">
               <Avatar className="h-8 w-8 shrink-0">
                <AvatarFallback className="bg-secondary"><Bot className="h-4 w-4" /></AvatarFallback>
              </Avatar>
              <div className="rounded-lg px-4 py-2 bg-muted flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-foreground/40 animate-bounce" />
                <span className="w-2 h-2 rounded-full bg-foreground/40 animate-bounce" style={{ animationDelay: '0.2s' }} />
                <span className="w-2 h-2 rounded-full bg-foreground/40 animate-bounce" style={{ animationDelay: '0.4s' }} />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
      <div className="p-3 border-t bg-background">
        <form onSubmit={handleSubmit} className="flex gap-2 items-center">
          <Button type="button" variant="ghost" size="icon" className="shrink-0 text-muted-foreground">
            <Paperclip className="h-5 w-5" />
          </Button>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            className="flex-1"
            disabled={isLoading}
          />
          <Button type="submit" size="icon" disabled={!input.trim() || isLoading}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  )
}
