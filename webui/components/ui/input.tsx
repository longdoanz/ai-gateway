import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-xl border border-outline-variant/50 bg-white/70 backdrop-blur-sm px-3.5 py-2 text-sm text-on-surface transition-all outline-none placeholder:text-on-surface-variant/40 hover:border-outline-variant hover:bg-white/85 focus-visible:border-primary-container/70 focus-visible:ring-2 focus-visible:ring-primary-container/15 focus-visible:bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-error aria-invalid:ring-2 aria-invalid:ring-error/20",
        className
      )}
      {...props}
    />
  )
}

export { Input }
