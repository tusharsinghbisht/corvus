import { AlertDetail } from "@/components/alert-detail";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ attempt?: string | string[] }>;
}) {
  const { id } = await params;
  const { attempt } = await searchParams;
  return (
    <AlertDetail
      id={id}
      attemptId={typeof attempt === "string" ? attempt : undefined}
    />
  );
}
