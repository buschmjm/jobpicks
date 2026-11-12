import { Navigate } from "react-router-dom";

/** Redirect to the swipe deck. */
export function DeckHomeRedirect() {
  return <Navigate to="/deck" replace />;
}
