<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import VehicleCatalogFields from "../components/VehicleCatalogFields.vue";
import { apiFetch, clearAccessToken, restoreSession, type CurrentUser } from "../lib/api";

interface Catalog { id: string; manufacturer: string; model_name: string; model_year: number; display_name: string; }
interface Vehicle { id: string; catalog_id: string; display_name: string; }
interface Manual { id: string; title: string; manual_type: string; pdf_page_count: number; is_primary: boolean; }
interface Session { id: string; vehicle_id: string; manuals: Manual[]; }
interface Citation {
  manual_title: string;
  pdf_page_number?: number;
  quote_text: string;
  source_type?: string;
  source_url?: string;
}
interface ChatResponse { result_status: "GROUNDED" | "CLARIFYING" | "INSUFFICIENT_EVIDENCE" | "SAFETY_ESCALATION"; answer?: string; citations: Citation[]; escalation?: string; official_manual_url?: string; official_manual_label?: string; }
interface Message { role: "user" | "assistant"; text: string; citations?: Citation[]; officialManualUrl?: string; officialManualLabel?: string; }

const router = useRouter();
const user = ref<CurrentUser | null>(null);
const catalogs = ref<Catalog[]>([]);
const vehicles = ref<Vehicle[]>([]);
const manufacturer = ref("");
const modelName = ref("");
const modelYear = ref<number | "">("");
const session = ref<Session | null>(null);
const messages = ref<Message[]>([]);
const question = ref("");
const loading = ref(true);
const starting = ref(false);
const sending = ref(false);
const notice = ref("");
const error = ref("");

const manufacturers = computed(() => [...new Set(catalogs.value.map((catalog) => catalog.manufacturer))].sort());
const modelNames = computed(() => [...new Set(catalogs.value.filter((catalog) => catalog.manufacturer === manufacturer.value).map((catalog) => catalog.model_name))].sort());
const modelYears = computed(() => [...new Set(catalogs.value.filter((catalog) => catalog.manufacturer === manufacturer.value && catalog.model_name === modelName.value).map((catalog) => catalog.model_year))].sort((a, b) => b - a));
const selectedCatalog = computed(() => catalogs.value.find((catalog) => catalog.manufacturer === manufacturer.value && catalog.model_name === modelName.value && catalog.model_year === modelYear.value) ?? null);
const accountLabel = computed(() => !user.value ? "사용자" : user.value.role === "ADMIN" ? `관리자 ${user.value.display_name}` : user.value.display_name);

onMounted(async () => {
  try {
    const current = await restoreSession();
    if (!current.onboarding_completed) { await router.replace("/auth/callback"); return; }
    user.value = current;
    await loadData();
  } catch { await router.replace("/login"); }
  finally { loading.value = false; }
});
onBeforeUnmount(() => closeSession());

async function loadData(): Promise<void> {
  const [catalogResponse, vehicleResponse] = await Promise.all([
    apiFetch<Catalog[]>("/vehicle-catalog"), apiFetch<Vehicle[]>("/vehicles"),
  ]);
  catalogs.value = catalogResponse;
  vehicles.value = vehicleResponse;
}

async function updateManufacturer(value: string): Promise<void> {
  if (session.value) await closeSession();
  manufacturer.value = value; modelName.value = ""; modelYear.value = "";
}

async function updateModelName(value: string): Promise<void> {
  if (session.value) await closeSession();
  modelName.value = value; modelYear.value = "";
}

async function updateModelYear(value: number | ""): Promise<void> {
  if (session.value) await closeSession();
  modelYear.value = value;
}

async function vehicleForSelectedCatalog(): Promise<Vehicle> {
  const catalog = selectedCatalog.value;
  if (!catalog) throw new Error("제조사, 차종, 연식을 순서대로 선택해 주세요.");
  const existing = vehicles.value.find((vehicle) => vehicle.catalog_id === catalog.id);
  if (existing) return existing;
  const vehicle = await apiFetch<Vehicle>("/vehicles", {
    method: "POST",
    body: JSON.stringify({ catalog_id: catalog.id, nickname: catalog.display_name }),
  });
  vehicles.value.push(vehicle);
  return vehicle;
}

async function startSession(): Promise<void> {
  error.value = ""; notice.value = ""; starting.value = true;
  try {
    const vehicle = await vehicleForSelectedCatalog();
    await closeSession();
    const createdSession = await apiFetch<Session>("/chat-sessions", { method: "POST", body: JSON.stringify({ vehicle_id: vehicle.id }) });
    // 세션을 만든 직후 다시 조회해 현재 READY 연결 문서를 사이드바에 표시한다.
    // 관리자 변경 직후에도 세션 생성 응답에 남은 이전 목록을 보여 주지 않기 위한 갱신이다.
    const manuals = await apiFetch<Manual[]>(`/chat-sessions/${createdSession.id}/manuals`);
    session.value = { ...createdSession, manuals };
    messages.value = [{ role: "assistant", text: "선택한 차량의 준비된 PDF 매뉴얼과 공식 웹 안내를 함께 검색해 답합니다. 불편한 기능이나 화면 문구를 질문해 보세요." }];
  } catch (caught) { error.value = caught instanceof Error ? caught.message : "대화를 시작하지 못했습니다."; }
  finally { starting.value = false; }
}

async function closeSession(): Promise<void> {
  const id = session.value?.id;
  session.value = null;
  if (id) await apiFetch<void>(`/chat-sessions/${id}`, { method: "DELETE" }).catch(() => undefined);
}

async function returnToVehicleSelection(): Promise<void> {
  await closeSession();
  manufacturer.value = ""; modelName.value = ""; modelYear.value = "";
  messages.value = []; question.value = "";
  notice.value = "대화를 종료했습니다. 제조사, 차종, 연식 순으로 차량을 다시 선택해 주세요.";
}

async function ask(): Promise<void> {
  if (!session.value || !question.value.trim() || sending.value) return;
  const content = question.value.trim(); question.value = ""; sending.value = true; error.value = "";
  messages.value.push({ role: "user", text: content });
  try {
    const result = await apiFetch<ChatResponse>(`/chat-sessions/${session.value.id}/messages`, { method: "POST", body: JSON.stringify({ content }) });
    messages.value.push({ role: "assistant", text: result.answer || result.escalation || "답변을 준비하지 못했습니다.", citations: result.citations, officialManualUrl: result.official_manual_url, officialManualLabel: result.official_manual_label });
  } catch (caught) { error.value = caught instanceof Error ? caught.message : "질문을 처리하지 못했습니다."; }
  finally { sending.value = false; }
}

async function download(manual: Manual): Promise<void> {
  if (!session.value) return;
  const pdfTab = window.open("", "_blank");
  try {
    const data = await apiFetch<{ url: string }>(`/chat-sessions/${session.value.id}/manuals/${manual.id}/download-url`, { method: "POST" });
    if (pdfTab) pdfTab.location.href = data.url;
    else window.location.assign(data.url);
  } catch (caught) {
    pdfTab?.close();
    error.value = caught instanceof Error ? caught.message : "매뉴얼을 열지 못했습니다.";
  }
}

async function logout(): Promise<void> {
  await closeSession(); await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  clearAccessToken(); await router.replace("/login");
}
</script>

<template>
  <div class="user-page">
    <header class="admin-header"><RouterLink class="wordmark" to="/app">CarMe</RouterLink><nav aria-label="사용자 메뉴"><a class="active" href="#vehicle-filter">차량 선택</a><a v-if="user?.role === 'ADMIN'" href="/admin">관리자 화면</a></nav><div class="account-menu"><span>{{ accountLabel }}</span><button type="button" @click="logout">로그아웃</button></div></header>
    <main class="user-main">
      <section class="user-hero"><p class="kicker">MANUAL RAG TEST</p><h1>차량 매뉴얼<br />AI 도우미</h1><p>준비 완료된 차량을 선택하면 PDF 매뉴얼과 연결된 현대 공식 웹 안내를 함께 검색해 근거를 제공합니다.</p></section>
      <p v-if="notice" class="notice success" role="status">{{ notice }}</p><p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <section id="vehicle-filter" class="user-card"><div class="section-heading"><div><p class="section-label">01 · 차량 선택</p><h2>질문할 차량 찾기</h2></div><span>준비된 매뉴얼이 있는 차량만 표시</span></div><div v-if="loading" class="empty-state">선택 가능한 차량을 불러오는 중입니다.</div><template v-else-if="catalogs.length"><div class="vehicle-filter-form"><VehicleCatalogFields mode="filter" :disabled="!!session" :manufacturer="manufacturer" :model-name="modelName" :model-year="modelYear" :manufacturers="manufacturers" :model-names="modelNames" :model-years="modelYears" @update:manufacturer="updateManufacturer" @update:model-name="updateModelName" @update:model-year="updateModelYear" /></div><div v-if="selectedCatalog && !session" class="chat-start"><div><strong>{{ selectedCatalog.display_name }}</strong><span>{{ selectedCatalog.manufacturer }} · {{ selectedCatalog.model_year }}년형 · 준비된 PDF 매뉴얼을 근거로 검색합니다.</span></div><button class="button primary" :disabled="starting" type="button" @click="startSession">{{ starting ? "준비 중" : "매뉴얼로 질문하기" }}</button></div><p v-else-if="!session" class="selection-help">제조사, 차종, 연식을 순서대로 선택해 주세요.</p></template><div v-else class="empty-state">현재 준비된 매뉴얼이 연결된 차량이 없습니다.</div></section>
      <section v-if="session" class="chat-layout"><aside class="manual-panel"><p class="section-label">연결 문서</p><h2>{{ selectedCatalog?.display_name }}</h2><p>아래 PDF 매뉴얼과 연결된 현대 공식 웹 안내를 함께 검색합니다. 답변마다 실제 사용한 근거를 표시합니다.</p><button v-for="manual in session.manuals" :key="manual.id" class="manual-download" type="button" @click="download(manual)"><span><strong>{{ manual.title }}</strong><small>{{ manual.is_primary ? "대표 매뉴얼" : "연결 매뉴얼" }} · {{ manual.pdf_page_count }}쪽</small></span><b>PDF 열기</b></button></aside><section class="chat-panel"><div class="chat-title"><div><p class="section-label">02 · 문서 기반 질문</p><h2>무엇이 불편하신가요?</h2></div><button class="close-chat" type="button" @click="returnToVehicleSelection">차량 다시 선택</button></div><div class="messages"><article v-for="(message, index) in messages" :key="index" class="message" :class="message.role"><p>{{ message.text }}</p><a v-if="message.officialManualUrl" :href="message.officialManualUrl" class="citation-link official-manual-link" target="_blank" rel="noreferrer">{{ message.officialManualLabel || "현대 공식 웹 매뉴얼 열기" }}</a><div v-if="message.citations?.length" class="citations"><strong>매뉴얼 근거</strong><template v-for="citation in message.citations" :key="`${citation.manual_title}-${citation.source_url || citation.pdf_page_number}`"><a v-if="citation.source_url" :href="citation.source_url" class="citation-link" target="_blank" rel="noreferrer">{{ citation.manual_title }} · 현대 공식 웹 매뉴얼<br /><span>{{ citation.quote_text }}</span></a><button v-else type="button">{{ citation.manual_title }} · PDF {{ citation.pdf_page_number }}쪽<br /><span>{{ citation.quote_text }}</span></button></template></div></article></div><form class="ask-form" @submit.prevent="ask"><input v-model="question" :disabled="sending" maxlength="1000" placeholder="예: 블루투스 연결 방법을 알려줘" /><button class="button primary" :disabled="sending || !question.trim()" type="submit">{{ sending ? "검색 중" : "질문하기" }}</button></form></section></section>
    </main>
  </div>
</template>
