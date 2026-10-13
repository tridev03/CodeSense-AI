import { AlertCircle, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message: string;
  retry?: () => void;
  className?: string;
}

export function ErrorState({ title = "Something went wrong", message, retry, className }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-6 rounded-lg border border-red-900/30 bg-red-950/10",
        className
      )}
    >
      <AlertCircle className="h-10 w-10 text-red-500 mb-4" />
      <h3 className="text-lg font-medium text-red-400 mb-2">{title}</h3>
      <p className="text-sm text-red-300/80 max-w-sm mb-6">{message}</p>
      
      {retry && (
        <Button 
          variant="outline" 
          onClick={retry}
          className="border-red-900/50 text-red-400 hover:bg-red-950/30 hover:text-red-300"
        >
          <RefreshCcw className="mr-2 h-4 w-4" />
          Try Again
        </Button>
      )}
    </div>
  );
}
