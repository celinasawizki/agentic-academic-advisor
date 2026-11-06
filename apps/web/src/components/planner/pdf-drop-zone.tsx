"use client"

import { FileUp, Loader2 } from "lucide-react"
import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"

const hasFiles = (e: { dataTransfer: DataTransfer | null }) => Array.from(e.dataTransfer?.types ?? []).includes("Files")
const isPdf = (f: File) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")

/** Click-or-drop PDF upload. While mounted, a file dropped anywhere else on the page is
 *  ignored instead of making the browser open it (which would leave the page and lose the form). */
export function PdfDropZone({ title, hint, busy, disabled, onFile }: {
  title: ReactNode
  hint: ReactNode
  busy?: boolean
  /** Shown dimmed and the file picker does not open; a dropped file is still passed to onFile so it can explain why. */
  disabled?: boolean
  onFile: (file: File) => void
}) {
  const [over, setOver] = useState(false)
  const depth = useRef(0) // dragenter/leave fire for every child element

  useEffect(() => {
    const guard = (e: globalThis.DragEvent) => { if (hasFiles(e)) e.preventDefault() }
    window.addEventListener("dragover", guard)
    window.addEventListener("drop", guard)
    return () => { window.removeEventListener("dragover", guard); window.removeEventListener("drop", guard) }
  }, [])

  const take = (files: FileList | null | undefined) => {
    const list = Array.from(files ?? [])
    if (!list.length) return
    const pdf = list.find(isPdf)
    if (!pdf) return toast.error(`${list[0].name} is not a PDF. Upload the PDF file.`)
    if (list.length > 1) toast.message(`Using ${pdf.name}; drop one file at a time.`)
    onFile(pdf)
  }

  const onDragEnter = (e: DragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    depth.current += 1
    setOver(true)
  }
  const onDragOver = (e: DragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "copy"
  }
  const onDragLeave = () => {
    depth.current = Math.max(0, depth.current - 1)
    if (depth.current === 0) setOver(false)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    depth.current = 0
    setOver(false)
    if (!busy) take(e.dataTransfer.files)
  }

  return (
    <label
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      aria-disabled={disabled || busy}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors hover:bg-muted/50",
        over && "border-primary bg-cherry-soft",
        (disabled || busy) && "cursor-not-allowed opacity-50 hover:bg-transparent",
      )}
    >
      {busy ? <Loader2 className="size-6 animate-spin text-primary" /> : <FileUp className="size-6 text-primary" />}
      <span className="text-sm font-medium">{over ? "Drop the PDF to upload" : title}</span>
      <span className="text-xs text-muted-foreground">{hint}</span>
      <input
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        disabled={disabled || busy}
        onChange={(e) => { take(e.target.files); e.target.value = "" }}
      />
    </label>
  )
}
