import { ResumePanel } from "../components/ResumePanel";
import { PageHeader } from "../components/ui/PageHeader";

export function AdvisorProfilePage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col pb-2">
      <PageHeader
        title="Profile"
        subtitle="Contact details, experience, and education used on resumes and by the advisor."
      />
      <ResumePanel variant="page" />
    </div>
  );
}
