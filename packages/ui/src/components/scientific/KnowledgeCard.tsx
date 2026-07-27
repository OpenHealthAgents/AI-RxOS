import * as React from "react"
import { Card, CardHeader, CardTitle, CardContent } from "../ui/card"
import { Badge } from "../ui/badge"

export interface KnowledgeCardProps {
  title: string
  type: "Gene" | "Disease" | "Pathway" | "Compound" | "Protein"
  description: string
  metadata?: Record<string, string | number>
}

const TYPE_COLORS: Record<KnowledgeCardProps["type"], string> = {
  Gene: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800",
  Disease: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800",
  Pathway: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800",
  Compound: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-200 dark:border-purple-800",
  Protein: "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-200 dark:border-orange-800",
}

export function KnowledgeCard({
  title,
  type,
  description,
  metadata = {},
}: KnowledgeCardProps) {
  return (
    <Card className="hover:border-primary/50 transition-colors h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start gap-2">
          <CardTitle className="text-lg">{title}</CardTitle>
          <div className={`text-xs px-2 py-0.5 rounded-full border font-medium shrink-0 ${TYPE_COLORS[type]}`}>
            {type}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4">
        <p className="text-sm text-muted-foreground line-clamp-4">
          {description}
        </p>
        {Object.keys(metadata).length > 0 && (
          <div className="mt-auto pt-4 border-t grid grid-cols-2 gap-2 text-xs">
            {Object.entries(metadata).map(([key, value]) => (
              <div key={key} className="flex flex-col">
                <span className="text-muted-foreground capitalize">{key}</span>
                <span className="font-medium truncate" title={String(value)}>{value}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
