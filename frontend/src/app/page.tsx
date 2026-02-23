import Sidebar from "@/components/Sidebar";
import ChatArea from "@/components/ChatArea";
import ApiKeyModal from "@/components/ApiKeyModal";
import { AppStateProvider } from "@/lib/AppStateContext";

export default function Home() {
  return (
    <AppStateProvider>
      <ApiKeyModal />
      <main className="flex h-screen w-full bg-background overflow-hidden selection:bg-primary/30">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 bg-[#0b0c0f] rounded-l-3xl border-l border-white/5 shadow-2xl overflow-hidden relative z-10">
          <ChatArea />
        </div>
      </main>
    </AppStateProvider>
  );
}
