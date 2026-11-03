"use client"

import { GraduationCap } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"

import { cn } from "@/lib/utils"

const NAV = [
  { href: "/onboarding", label: "Build my schedule" },
  { href: "/demo", label: "Demo" },
  { href: "/advisor", label: "Advisor view" },
  { href: "/architecture", label: "How it works" },
]

export function SiteHeader() {
  const path = usePathname()
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <GraduationCap className="size-4.5" />
          </span>
          <span className="hidden sm:inline">
            Temple <span className="text-primary">Academic Planning</span> AI
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                path.startsWith(n.href) && "bg-muted font-medium text-foreground",
              )}
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  )
}
