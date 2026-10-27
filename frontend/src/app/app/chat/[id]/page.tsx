"use client";

import { use } from "react";
import { ChatView } from "@/components/chat-view";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RepositoryChatPage({ params }: PageProps) {
  const { id } = use(params);
  return <ChatView initialRepoId={id} showRepoSelector={true} />;
}
