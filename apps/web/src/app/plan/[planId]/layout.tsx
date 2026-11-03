import { Loader2 } from "lucide-react"
import { Suspense } from "react"

import { PlanShell } from "@/components/planner/plan-context"

async function Shell({ params, children }: { params: LayoutProps<"/plan/[planId]">["params"]; children: React.ReactNode }) {
  const { planId } = await params
  return <PlanShell planId={planId}>{children}</PlanShell>
}

export default function PlanLayout({ children, params }: LayoutProps<"/plan/[planId]">) {
  return (
    <Suspense fallback={<div className="flex justify-center py-24"><Loader2 className="size-6 animate-spin text-primary" /></div>}>
      <Shell params={params}>{children}</Shell>
    </Suspense>
  )
}
