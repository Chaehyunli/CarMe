<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { apiFetch, restoreSession, type CurrentUser, type UserRole } from "../lib/api";

const router = useRouter();
const loading = ref(true);
const error = ref("");
const user = ref<CurrentUser | null>(null);
const selectedRole = ref<UserRole>("USER");
const adminCode = ref("");
const saving = ref(false);

onMounted(async () => {
  try {
    const sessionUser = await restoreSession();
    user.value = sessionUser;
    if (sessionUser.onboarding_completed) {
      await router.replace(sessionUser.role === "ADMIN" ? "/admin" : "/welcome");
    }
  } catch {
    error.value = "로그인 정보를 확인하지 못했습니다. 다시 로그인해 주세요.";
  } finally {
    loading.value = false;
  }
});

async function submitRole(): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    const updatedUser = await apiFetch<CurrentUser>("/auth/onboarding", {
      method: "POST",
      body: JSON.stringify({ role: selectedRole.value, admin_code: adminCode.value || undefined }),
    });
    await restoreSession();
    await router.replace(updatedUser.role === "ADMIN" ? "/admin" : "/welcome");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "역할을 저장하지 못했습니다.";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <main class="callback-page">
    <p v-if="loading" class="loading-message">로그인 정보를 안전하게 확인하고 있습니다.</p>
    <section v-else-if="error && !user" class="message-card" aria-live="polite">
      <h1>로그인을 완료하지 못했습니다</h1>
      <p>{{ error }}</p>
      <RouterLink class="button secondary" to="/login">로그인 화면으로</RouterLink>
    </section>

    <div v-else class="modal-backdrop">
      <section class="role-modal" role="dialog" aria-modal="true" aria-labelledby="role-title">
        <p class="section-label">첫 로그인 설정</p>
        <h1 id="role-title">어떻게 CarMe를 이용하시나요?</h1>
        <p class="modal-intro">이 선택은 계정 생성 시 한 번만 저장됩니다.</p>
        <div class="role-options">
          <label class="role-option" :class="{ selected: selectedRole === 'USER' }"><input v-model="selectedRole" type="radio" value="USER" /><span><strong>운전자</strong><small>내 차량 매뉴얼을 찾아보고 AI 도우미를 이용합니다.</small></span></label>
          <label class="role-option" :class="{ selected: selectedRole === 'ADMIN' }"><input v-model="selectedRole" type="radio" value="ADMIN" /><span><strong>관리자</strong><small>차량 카탈로그와 공식 매뉴얼을 등록·관리합니다.</small></span></label>
        </div>
        <label v-if="selectedRole === 'ADMIN'" class="field"><span>관리자 코드</span><input v-model="adminCode" autocomplete="one-time-code" type="password" placeholder="관리자 코드를 입력하세요" /></label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="button primary wide" :disabled="saving" type="button" @click="submitRole">{{ saving ? "저장 중" : "선택 완료" }}</button>
      </section>
    </div>
  </main>
</template>
