/**
 * Chat tab slice — Order 5 placeholder + Order 8's editing/streaming fields.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export interface ChatSlice {
  chatActiveSessionId: string | null;
  chatActiveBranchId: string | null;
  chatEditingMessageId: string | null;
  /**
   * Token buffer keyed by message_id. Order 8's WS handler appends
   * tokens here and the MessageBubble subscribes to ``[messageId]`` so
   * only the bubble re-renders during streaming.
   */
  chatStreamingTokens: Record<string, string>;
  setChatActiveSession: (id: string | null) => void;
  setChatActiveBranch: (id: string | null) => void;
  setChatEditingMessage: (id: string | null) => void;
  appendChatToken: (messageId: string, token: string) => void;
  flushChatTokens: (messageId: string) => void;
}

export const createChatSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  ChatSlice
> = (set) => ({
  chatActiveSessionId: null,
  chatActiveBranchId: null,
  chatEditingMessageId: null,
  chatStreamingTokens: {},
  setChatActiveSession: (id) =>
    set({
      chatActiveSessionId: id,
      chatActiveBranchId: null,
      chatStreamingTokens: {},
    }),
  setChatActiveBranch: (id) =>
    // Order 8 audit Finding #6: branch switch must drop in-flight
    // streaming tokens — they belong to the branch we just left.
    set({ chatActiveBranchId: id, chatStreamingTokens: {} }),
  setChatEditingMessage: (id) => set({ chatEditingMessageId: id }),
  appendChatToken: (messageId, token) =>
    set((state) => ({
      chatStreamingTokens: {
        ...state.chatStreamingTokens,
        [messageId]: (state.chatStreamingTokens[messageId] ?? "") + token,
      },
    })),
  flushChatTokens: (messageId) =>
    set((state) => {
      // Drop the entry rather than write an empty string — keeps the
      // dict bounded and frees memory for long-lived chat sessions.
      const { [messageId]: _flushed, ...rest } = state.chatStreamingTokens;
      void _flushed;
      return { chatStreamingTokens: rest };
    }),
});
