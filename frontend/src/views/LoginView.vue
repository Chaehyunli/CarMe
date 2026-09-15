<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { apiUrl, restoreSession } from "../lib/api";

const router = useRouter();
const route = useRoute();
const checkingSession = ref(true);
const error = ref(route.query.error === "kakao_login_failed" ? "카카오 로그인에 실패했습니다. 다시 시도해 주세요." : "");

onMounted(async () => {
  try {
    const user = await restoreSession();
    if (user.onboarding_completed) await router.replace(user.role === "ADMIN" ? "/admin" : "/welcome");
  } catch {
    // A first visit has no refresh cookie, which is the expected state.
  } finally {
    checkingSession.value = false;
  }
});

function beginKakaoLogin(): void {
  window.location.assign(apiUrl("/auth/kakao/start"));
}
</script>

<template>
  <main class="login-layout">
    <section class="login-intro" aria-labelledby="login-title">
      <a class="wordmark" href="/login">CarMe</a>
      <div class="login-copy">
        <p class="kicker">HYUNDAI MANUAL INTELLIGENCE</p>
        <h1 id="login-title">차량 매뉴얼을<br />더 가까이.</h1>
        <p>현대자동차 차량별 공식 매뉴얼을 바탕으로 필요한 정보를 찾는 AI 도우미입니다.</p>
      </div>
      <p class="login-note">처음 로그인한 뒤 이용 목적을 선택합니다.</p>
    </section>

    <section class="login-panel" aria-label="로그인">
      <div class="login-card">
        <p class="section-label">CARME 시작하기</p>
        <h2>카카오로 로그인</h2>
        <p>안전한 계정 연결 후 바로 시작할 수 있습니다.</p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="kakao-button" :disabled="checkingSession" type="button" @click="beginKakaoLogin">
          <span aria-hidden="true">K</span>
          {{ checkingSession ? "로그인 상태 확인 중" : "카카오로 계속하기" }}
        </button>
        <p class="helper-text">관리자 등록은 최초 로그인 뒤 관리자 코드 확인을 거쳐서만 가능합니다.</p>
      </div>
    </section>
  </main>
</template>
