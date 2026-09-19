"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Preference, type UserSelf } from "@/lib/api";
import { useUnsavedChanges } from "@/lib/hooks";
import { ErrorMessage, Field, Submit, Toggle } from "./ui";

export function PreferencesForm({ preferences, userId }: { preferences: Preference; userId: string }) {
  const client = useQueryClient();
  const [draft, setForm] = useState<Preference | null>(null);
  const form = draft || preferences;
  const dirty = JSON.stringify(form) !== JSON.stringify(preferences);
  const command = useMutation({
    mutationFn: (value: Preference) => api<Preference>("/me/preferences", { method: "PATCH", body: JSON.stringify({
      revision: value.revision, coffee_chat_available: value.coffee_chat_available,
      project_available: value.project_available, learning_stage: value.learning_stage,
      activity_goal: value.activity_goal, hours_per_week: value.hours_per_week,
      collaboration_mode: value.collaboration_mode, is_public: value.is_public,
    }) }),
    onMutate: () => client.cancelQueries({ queryKey: ["me"], exact: true }),
    onSuccess: async saved => {
      // Cancel a focus-triggered read too, then use the authoritative PATCH response.
      await client.cancelQueries({ queryKey: ["me"], exact: true });
      if (client.getQueryData<UserSelf>(["me"])?.id !== userId) return;
      client.setQueryData<UserSelf>(["me"], current => current?.id === userId ? { ...current, preferences: saved } : current);
      setForm(null);
      // Other views refresh independently; a failed refetch must not undo a successful save.
      void client.invalidateQueries();
    },
  });
  useUnsavedChanges(dirty && !command.isPending);
  return <section className="panel" id="preferences"><h2>어떤 연결을 찾고 있나요?</h2><form className="stack" onSubmit={e => { e.preventDefault(); command.mutate(form); }}><fieldset className="stack preference-fields" disabled={command.isPending}><Toggle label="커피챗 요청을 받을게요" checked={form.coffee_chat_available} onChange={v => setForm({ ...form, coffee_chat_available: v })} /><Toggle label="프로젝트에 참여할 수 있어요" checked={form.project_available} onChange={v => setForm({ ...form, project_available: v })} /><Field label="지금의 학습 단계"><select value={form.learning_stage} onChange={e => setForm({ ...form, learning_stage: e.target.value })}><option value="exploring">아직 탐색 중</option><option value="starting">처음 시작해요</option><option value="learning">기초를 배우고 있어요</option><option value="building">작은 기능을 만들어 봤어요</option><option value="experienced">프로젝트 경험이 있어요</option></select></Field><Field label="함께 이루고 싶은 목표"><input value={form.activity_goal} maxLength={1000} placeholder="첫 프로젝트 완성, 함께 공부하기…" onChange={e => setForm({ ...form, activity_goal: e.target.value })} /></Field><div className="form-grid"><Field label="주당 가능한 시간"><input type="number" min={0} max={168} value={form.hours_per_week ?? ""} onChange={e => setForm({ ...form, hours_per_week: e.target.value ? Number(e.target.value) : null })} /></Field><Field label="협업 방식"><select value={form.collaboration_mode} onChange={e => setForm({ ...form, collaboration_mode: e.target.value })}><option value="flexible">협의 가능</option><option value="online">온라인</option><option value="offline">오프라인</option><option value="hybrid">온·오프라인</option></select></Field></div><Toggle label="활동 조건 공개" checked={form.is_public} onChange={v => setForm({ ...form, is_public: v })} /></fieldset><ErrorMessage error={command.error} /><div className="form-actions">{dirty ? <span className="muted" role="status">아직 저장하지 않았어요</span> : command.isSuccess && <span role="status" className="badge green">저장했어요</span>}<Submit pending={command.isPending}>활동 조건 저장</Submit></div></form><p className="muted">본인이 입력한 정보이며, AI가 검증한 실력으로 표시하지 않습니다.</p></section>;
}
