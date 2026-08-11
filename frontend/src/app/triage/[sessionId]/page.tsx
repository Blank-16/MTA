import { notFound } from "next/navigation";

interface Props {
  params: { sessionId: string };
}

export default async function SessionPage({ params }: Props) {
  const { sessionId } = params;

  // UUID validation before hitting the DB
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!uuidRegex.test(sessionId)) notFound();

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-xl font-semibold">Session {sessionId.slice(0, 8)}&hellip;</h1>
      <p className="text-sm text-muted-foreground">Session history view — connect to DB to load messages.</p>
    </div>
  );
}
