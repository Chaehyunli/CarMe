<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { apiFetch, clearAccessToken, restoreSession, type CurrentUser } from "../lib/api";

const router = useRouter();
const user = ref<CurrentUser | null>(null);

onMounted(async () => {
  try {
    const current = await restoreSession();
    if (!current.onboarding_completed) {
      await router.replace("/auth/callback");
      return;
    }
    if (current.role === "ADMIN") {
      await router.replace("/admin");
      return;
    }
    user.value = current;
  } catch {
    await router.replace("/login");
  }
});

async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  clearAccessToken();
  await router.replace("/login");
}
</script>

<template>
  <main class="callback-page">
    <section v-if="user" class="message-card">
      <p class="section-label">CARME 계정 설정 완료</p>
      <h1>{{ user.display_name }}님, 반갑습니다.</h1>
      <p>이용자 계정이 준비되었습니다. 차량 선택과 AI 도우미 화면은 다음 개발 단계에서 연결됩니다.</p>
      <button class="button secondary" type="button" @click="logout">로그아웃</button>
    </section>
  </main>
</template>
