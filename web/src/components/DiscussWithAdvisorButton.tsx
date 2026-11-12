import { useNavigate } from "react-router-dom";
import { Button } from "./ui/Button";
import { DISCUSS_JOB_STATE_KEY } from "../lib/discussJob";
import type { MatchCard } from "../types";

interface DiscussWithAdvisorButtonProps {
  card: MatchCard;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  fullWidth?: boolean;
  className?: string;
  onNavigating?: () => void;
}

export function DiscussWithAdvisorButton({
  card,
  variant = "secondary",
  size = "sm",
  fullWidth = false,
  className = "",
  onNavigating,
}: DiscussWithAdvisorButtonProps) {
  const navigate = useNavigate();

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      fullWidth={fullWidth}
      className={className}
      onClick={() => {
        onNavigating?.();
        navigate("/advisor/chat", { state: { [DISCUSS_JOB_STATE_KEY]: card } });
      }}
    >
      Discuss with Advisor
    </Button>
  );
}
