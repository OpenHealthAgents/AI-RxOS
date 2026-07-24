import * as React from "react"
import ForceGraph2D, { ForceGraphProps } from "react-force-graph-2d"

export interface GraphViewerProps extends ForceGraphProps {
  data: {
    nodes: any[]
    links: any[]
  }
  width?: number
  height?: number
}

export function GraphViewer({ data, width = 800, height = 600, ...props }: GraphViewerProps) {
  const fgRef = React.useRef<any>()

  React.useEffect(() => {
    // Optional: add custom forces or behavior on mount
    if (fgRef.current) {
      fgRef.current.d3Force('charge').strength(-120)
    }
  }, [])

  return (
    <div className="border rounded-md overflow-hidden bg-background">
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        width={width}
        height={height}
        nodeLabel="id"
        nodeColor={(node: any) => node.color || "hsl(var(--primary))"}
        linkColor={() => "hsl(var(--border))"}
        backgroundColor="hsl(var(--background))"
        {...props}
      />
    </div>
  )
}
