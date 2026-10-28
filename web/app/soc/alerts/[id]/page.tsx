import { AlertDetail } from "@/components/alert-detail";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <AlertDetail id={id} />;
}
