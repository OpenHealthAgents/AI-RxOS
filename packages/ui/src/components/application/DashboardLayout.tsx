import * as React from "react"
import { Menu, Bell, User } from "lucide-react"
import { Button } from "../ui/button"

export interface DashboardLayoutProps {
  sidebar: React.ReactNode
  header?: React.ReactNode
  children: React.ReactNode
}

export function DashboardLayout({ sidebar, header, children }: DashboardLayoutProps) {
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(true)

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${
          isSidebarOpen ? "w-64" : "w-0"
        } transition-all duration-300 ease-in-out border-r bg-card flex-shrink-0 overflow-hidden flex flex-col`}
      >
        <div className="h-14 border-b flex items-center px-4 font-semibold text-lg shrink-0">
          AI-RxOS
        </div>
        <div className="flex-1 overflow-y-auto">
          {sidebar}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <header className="h-14 border-b bg-card flex items-center justify-between px-4 shrink-0">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            {header}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon">
              <Bell className="h-5 w-5" />
            </Button>
            <Button variant="ghost" size="icon" className="rounded-full bg-muted">
              <User className="h-5 w-5" />
            </Button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="mx-auto max-w-7xl h-full">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
