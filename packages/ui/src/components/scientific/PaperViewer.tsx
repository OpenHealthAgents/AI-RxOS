import * as React from "react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../ui/card"
import { Badge } from "../ui/badge"
import { ScrollArea } from "../ui/scroll-area"
import { Button } from "../ui/button"
import { FileText, ExternalLink, Download } from "lucide-react"

export interface PaperViewerProps {
  title: string
  authors: string[]
  abstract: string
  journal?: string
  year?: string | number
  doi?: string
  pdfUrl?: string
}

export function PaperViewer({
  title,
  authors,
  abstract,
  journal,
  year,
  doi,
  pdfUrl,
}: PaperViewerProps) {
  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <div className="flex justify-between items-start gap-4">
          <div>
            <CardTitle className="text-xl leading-tight mb-2">{title}</CardTitle>
            <CardDescription className="text-sm text-foreground/80">
              {authors.join(", ")}
            </CardDescription>
            <div className="flex items-center gap-2 mt-2">
              {journal && <Badge variant="secondary">{journal}</Badge>}
              {year && <Badge variant="outline">{year}</Badge>}
            </div>
          </div>
          <div className="flex flex-col gap-2 shrink-0">
            {doi && (
              <Button variant="outline" size="sm" asChild>
                <a href={`https://doi.org/${doi}`} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" /> DOI
                </a>
              </Button>
            )}
            {pdfUrl && (
              <Button variant="default" size="sm" asChild>
                <a href={pdfUrl} target="_blank" rel="noreferrer">
                  <Download className="mr-2 h-4 w-4" /> PDF
                </a>
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden flex flex-col">
        <h4 className="font-semibold mb-2 flex items-center">
          <FileText className="mr-2 h-4 w-4" /> Abstract
        </h4>
        <ScrollArea className="flex-1 rounded-md border p-4 bg-muted/20">
          <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
            {abstract}
          </p>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
