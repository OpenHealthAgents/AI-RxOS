import * as React from "react"
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "../ui/card"
import { Badge } from "../ui/badge"

export interface DrugCardProps {
  name: string
  chemblId?: string
  smiles?: string
  synonyms?: string[]
  targets?: string[]
  phase?: number
  imageSrc?: string
}

export function DrugCard({
  name,
  chemblId,
  smiles,
  synonyms = [],
  targets = [],
  phase,
  imageSrc,
}: DrugCardProps) {
  return (
    <Card className="overflow-hidden transition-all hover:shadow-md">
      <CardHeader className="bg-muted/30 pb-4">
        <div className="flex justify-between items-start">
          <CardTitle className="text-lg text-primary">{name}</CardTitle>
          {phase !== undefined && (
            <Badge variant={phase === 4 ? "default" : "secondary"}>
              Phase {phase}
            </Badge>
          )}
        </div>
        {chemblId && (
          <p className="text-xs text-muted-foreground font-mono">{chemblId}</p>
        )}
      </CardHeader>
      <CardContent className="pt-4 grid gap-4">
        {imageSrc ? (
          <div className="flex justify-center bg-white p-2 rounded-md border">
            <img src={imageSrc} alt={`Structure of ${name}`} className="h-32 object-contain mix-blend-multiply" />
          </div>
        ) : smiles ? (
          <div className="text-xs font-mono break-all bg-muted p-2 rounded-md border text-muted-foreground line-clamp-3">
            {smiles}
          </div>
        ) : null}
        
        {targets.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold mb-2 uppercase tracking-wider text-muted-foreground">Known Targets</h4>
            <div className="flex flex-wrap gap-1">
              {targets.map(t => (
                <Badge key={t} variant="outline" className="text-[10px] py-0">{t}</Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
      {synonyms.length > 0 && (
        <CardFooter className="bg-muted/10 border-t pt-4 text-xs text-muted-foreground">
          <span className="line-clamp-1" title={synonyms.join(", ")}>
            <span className="font-semibold mr-1">Also known as:</span>
            {synonyms.join(", ")}
          </span>
        </CardFooter>
      )}
    </Card>
  )
}
