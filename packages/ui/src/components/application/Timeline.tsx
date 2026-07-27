import * as React from "react"

export interface TimelineEvent {
  id: string
  title: string
  date: string
  description?: string
  status?: "completed" | "current" | "upcoming" | "error"
}

export interface TimelineProps {
  events: TimelineEvent[]
}

export function Timeline({ events }: TimelineProps) {
  return (
    <div className="relative border-l border-muted ml-3 py-2 space-y-6">
      {events.map((event, index) => {
        let dotColor = "bg-muted border-background"
        if (event.status === "completed") dotColor = "bg-primary border-primary/20"
        if (event.status === "current") dotColor = "bg-blue-500 border-blue-200"
        if (event.status === "error") dotColor = "bg-destructive border-destructive/20"

        return (
          <div key={event.id} className="relative pl-6">
            <span
              className={`absolute -left-1.5 top-1.5 h-3 w-3 rounded-full border-2 ring-2 ring-background ${dotColor}`}
            />
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground font-medium">
                {event.date}
              </span>
              <h4 className="text-sm font-semibold">{event.title}</h4>
              {event.description && (
                <p className="text-sm text-muted-foreground mt-1">
                  {event.description}
                </p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
