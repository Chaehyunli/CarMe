import { createApp } from "vue";
import { VueQueryPlugin } from "@tanstack/vue-query";

import App from "./App.vue";
import { apiFetch } from "./lib/api";
import { router } from "./router";
import "./styles.css";

// 첫 렌더링에서 API 도달 가능 여부만 가볍게 확인한다. 로그인 여부와 무관한 공개 상태 API다.
void apiFetch<void>("/health").catch(() => undefined);

createApp(App).use(router).use(VueQueryPlugin).mount("#app");
