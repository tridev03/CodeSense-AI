import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 rounded-lg border border-[#242424] bg-surface-2",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber/10 text-amber mb-4">
        {icon}
      </div>
      <h3 className="text-lg font-medium text-white mb-2">{title}</h3>
      <p className="text-sm text-zinc-400 max-w-sm mb-6">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}
