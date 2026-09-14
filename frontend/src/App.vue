<script setup lang="ts">
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
</script>

<template>
  <main class="app-shell">
    <p class="eyebrow">CarMe</p>
    <h1>내 차 매뉴얼을 더 쉽게</h1>
    <p>선택한 차량에 적용되는 공식 매뉴얼에서 근거를 찾아 안내합니다.</p>
    <p class="status">API 연결 대상: {{ apiBaseUrl }}</p>
  </main>
</template>
