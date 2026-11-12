import { ResumeBuilderPanel } from "../components/ResumeBuilderPanel";
import { PageHeader } from "../components/ui/PageHeader";

export function AdvisorGeneratorPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col pb-2">
      <PageHeader
        title="Resume generator"
        subtitle="Build a full ATS resume or tailor one to a job you discussed."
      />
      <ResumeBuilderPanel variant="page" />
    </div>
  );
}
