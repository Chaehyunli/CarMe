import { createRouter, createWebHistory } from "vue-router";

import AdminView from "./views/AdminView.vue";
import AuthCallbackView from "./views/AuthCallbackView.vue";
import LoginView from "./views/LoginView.vue";
import UserWelcomeView from "./views/UserWelcomeView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/login" },
    { path: "/login", component: LoginView },
    { path: "/auth/callback", component: AuthCallbackView },
    { path: "/admin", component: AdminView },
    { path: "/welcome", component: UserWelcomeView },
  ],
});
