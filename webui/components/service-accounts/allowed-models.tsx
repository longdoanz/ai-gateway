import { ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function AllowedModelsBadges({
  models,
  max = 3,
}: {
  models: string[];
  max?: number;
}) {
  if (models.length === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-error whitespace-nowrap">
        <ShieldAlert className="w-3 h-3" /> 0 models
      </span>
    );
  }

  const shown = models.slice(0, max);
  const hidden = models.slice(max);

  return (
    <div className="flex flex-wrap gap-1 max-w-xs">
      {shown.map((m) => (
        <Badge key={m} variant="secondary" className="font-mono text-[11px]">
          {m}
        </Badge>
      ))}
      {hidden.length > 0 && (
        <Badge variant="secondary" className="text-[11px]" title={hidden.join(", ")}>
          +{hidden.length} more
        </Badge>
      )}
    </div>
  );
}
