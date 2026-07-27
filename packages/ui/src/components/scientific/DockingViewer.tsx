import * as React from "react"

export interface DockingViewerProps {
  pdbUrl?: string
  structureData?: string
  width?: number | string
  height?: number | string
}

export function DockingViewer({ pdbUrl, structureData, width = "100%", height = "500px" }: DockingViewerProps) {
  const viewerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    let viewer: any;
    
    const initViewer = async () => {
      // Dynamic import to avoid SSR issues if used in Next.js without next/dynamic
      if (typeof window !== "undefined") {
        try {
          // Initialize Molstar viewer
          // Note: Molstar requires a bit more complex setup in a real app, this is a placeholder wrapper structure
          // to show where the initialization logic would go.
          const { Viewer } = await import("molstar/build/viewer/molstar")
          
          if (viewerRef.current) {
            viewer = new Viewer(viewerRef.current, {
              layoutIsExpanded: false,
              layoutShowControls: true,
              layoutShowRemoteState: false,
              layoutShowSequence: true,
              layoutShowLog: false,
              layoutShowLeftPanel: true,
            })
            
            if (pdbUrl) {
              viewer.loadPdb(pdbUrl)
            } else if (structureData) {
              viewer.loadStructureFromData(structureData, 'pdb')
            }
          }
        } catch (e) {
          console.error("Failed to initialize Molstar viewer", e)
        }
      }
    }
    
    initViewer()

    return () => {
      if (viewer) {
        // Cleanup logic if supported by molstar
      }
    }
  }, [pdbUrl, structureData])

  return (
    <div className="border rounded-md overflow-hidden bg-black relative" style={{ width, height }}>
      <div ref={viewerRef} className="absolute inset-0 w-full h-full" />
    </div>
  )
}
