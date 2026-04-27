import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border font-mono-label text-mono-label font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:ring-2 focus-visible:ring-ring/40 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary-container text-on-primary shadow-[0_2px_8px_rgba(79,70,229,0.2)] hover:bg-primary-container/90 hover:-translate-y-[1px] hover:shadow-[0_4px_14px_rgba(79,70,229,0.28)] active:translate-y-0 active:shadow-none",
        outline:
          "border-outline-variant/60 bg-white/70 backdrop-blur-sm text-on-surface shadow-[0_1px_3px_rgba(0,0,0,0.05)] hover:bg-white/90 hover:-translate-y-[1px] hover:border-outline-variant hover:shadow-[0_3px_10px_rgba(0,0,0,0.08)]",
        secondary:
          "border-transparent bg-surface-container text-on-surface hover:bg-surface-container-high hover:-translate-y-[1px]",
        ghost:
          "border-transparent hover:bg-surface-container text-on-surface-variant hover:text-on-surface",
        destructive:
          "border-transparent bg-error/10 text-error hover:bg-error/15 focus-visible:ring-error/30",
        link: "border-transparent text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 gap-2 px-4",
        xs: "h-6 gap-1 rounded-md px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-md px-3 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-11 gap-2 px-5 text-sm",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8 rounded-md",
        "icon-lg": "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
