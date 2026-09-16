<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { apiFetch, clearAccessToken, restoreSession, type CurrentUser } from "../lib/api";
import VehicleCatalogFields from "../components/VehicleCatalogFields.vue";

interface Catalog {
  id: string;
  manufacturer: string;
  model_name: string;
  model_year: number;
  display_name: string;
  official_manual_url?: string;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  ready_manual_count: number;
}

interface Manual {
  id: string;
  title: string;
  manual_type: string;
  locale: string;
  status: string;
  original_filename: string;
  file_size_bytes: number;
  pdf_page_count: number;
  catalog_ids: string[];
  primary_catalog_ids: string[];
  applicable_catalogs: string[];
  indexing_total_chunks: number;
  embedded_chunk_count: number;
}
interface OfficialSource { id: string; }

const router = useRouter();
const user = ref<CurrentUser | null>(null);
const catalogs = ref<Catalog[]>([]);
const manuals = ref<Manual[]>([]);
const loading = ref(true);
const notice = ref("");
const error = ref("");
const savingCatalog = ref(false);
const uploading = ref(false);
const preparingManualId = ref<string | null>(null);
const catalogForm = ref({ manufacturer: "HYUNDAI", model_name: "", model_year: new Date().getFullYear() });
const manualForm = ref({ title: "", manual_type: "OWNER_MANUAL", locale: "ko-KR", catalog_ids: [] as string[] });
const makePrimary = ref(true);
const editingCatalogId = ref<string | null>(null);
const catalogEdit = ref({ manufacturer: "HYUNDAI", model_name: "", model_year: new Date().getFullYear() });
const editingManualId = ref<string | null>(null);
const manualEdit = ref({ title: "", manual_type: "OWNER_MANUAL", locale: "ko-KR", catalog_ids: [] as string[] });
const editManualPrimary = ref(false);
let progressTimer: ReturnType<typeof window.setInterval> | null = null;
const savingEdit = ref(false);
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const officialSourceCounts = ref<Record<string, number>>({});
const syncingOfficialCatalogId = ref<string | null>(null);
const selectedCatalogs = computed(() => catalogs.value.filter((catalog) => manualForm.value.catalog_ids.includes(catalog.id)));
const accountLabel = computed(() => {
  if (!user.value) return "사용자";
  return user.value.role === "ADMIN" ? `관리자 ${user.value.display_name}` : user.value.display_name;
});

onMounted(async () => {
  try {
    const current = await restoreSession();
    if (!current.onboarding_completed || current.role !== "ADMIN") {
      await router.replace("/login");
      return;
    }
    user.value = current;
    await loadData();
    progressTimer = window.setInterval(() => {
      if (manuals.value.some((manual) => manual.status === "INDEXING")) loadData().catch(() => undefined);
    }, 5000);
  } catch {
    await router.replace("/login");
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(() => { if (progressTimer) window.clearInterval(progressTimer); });

async function loadData(): Promise<void> {
  const [catalogResponse, manualResponse] = await Promise.all([
    apiFetch<Catalog[]>("/admin/vehicle-catalog"),
    apiFetch<Manual[]>("/admin/manuals"),
  ]);
  catalogs.value = catalogResponse;
  manuals.value = manualResponse;
  const counts = await Promise.all(catalogResponse.map(async (catalog) => {
    if (!catalog.official_manual_url) return [catalog.id, 0] as const;
    try {
      const sources = await apiFetch<OfficialSource[]>(`/admin/vehicle-catalog/${catalog.id}/official-sources`);
      return [catalog.id, sources.length] as const;
    } catch {
      return [catalog.id, 0] as const;
    }
  }));
  officialSourceCounts.value = Object.fromEntries(counts);
}

async function createCatalog(): Promise<void> {
  error.value = "";
  notice.value = "";
  savingCatalog.value = true;
  try {
    const catalog = await apiFetch<Catalog>("/admin/vehicle-catalog", {
      method: "POST",
      body: JSON.stringify(catalogForm.value),
    });
    catalogs.value.unshift(catalog);
    catalogForm.value.model_name = "";
    notice.value = `${catalog.display_name} 차량 초안을 만들었습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "차량을 저장하지 못했습니다.";
  } finally {
    savingCatalog.value = false;
  }
}

function beginCatalogEdit(catalog: Catalog): void {
  editingCatalogId.value = catalog.id;
  catalogEdit.value = {
    manufacturer: catalog.manufacturer,
    model_name: catalog.model_name,
    model_year: catalog.model_year,
  };
}

async function saveCatalogEdit(): Promise<void> {
  if (!editingCatalogId.value) return;
  error.value = "";
  savingEdit.value = true;
  try {
    const updated = await apiFetch<Catalog>(`/admin/vehicle-catalog/${editingCatalogId.value}`, {
      method: "PATCH",
      body: JSON.stringify(catalogEdit.value),
    });
    catalogs.value = catalogs.value.map((catalog) => (catalog.id === updated.id ? updated : catalog));
    editingCatalogId.value = null;
    notice.value = `${updated.display_name} 차량 초안을 수정했습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "차량을 수정하지 못했습니다.";
  } finally {
    savingEdit.value = false;
  }
}

async function deleteCatalog(catalog: Catalog): Promise<void> {
  if (!window.confirm(`${catalog.display_name} 차량 초안을 삭제할까요?`)) return;
  error.value = "";
  try {
    await apiFetch<void>(`/admin/vehicle-catalog/${catalog.id}`, { method: "DELETE" });
    catalogs.value = catalogs.value.filter((item) => item.id !== catalog.id);
    notice.value = `${catalog.display_name} 차량 초안을 삭제했습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "차량을 삭제하지 못했습니다.";
  }
}

function setFile(event: Event): void {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  if (file && (file.type !== "application/pdf" || !file.name.toLowerCase().endsWith(".pdf"))) {
    error.value = "PDF 파일만 업로드할 수 있습니다.";
    selectedFile.value = null;
    target.value = "";
    return;
  }
  selectedFile.value = file;
  if (file && !manualForm.value.title) manualForm.value.title = file.name.replace(/\.pdf$/i, "");
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function uploadManual(): Promise<void> {
  error.value = "";
  notice.value = "";
  const file = selectedFile.value;
  if (!file) {
    error.value = "업로드할 PDF 파일을 선택해 주세요.";
    return;
  }
  if (!manualForm.value.catalog_ids.length) {
    error.value = "이 매뉴얼을 적용할 차량을 하나 이상 선택해 주세요.";
    return;
  }
  uploading.value = true;
  try {
    const payload = {
      ...manualForm.value,
      primary_catalog_ids: makePrimary.value ? manualForm.value.catalog_ids : [],
      original_filename: file.name,
      sha256: await sha256(file),
      file_size_bytes: file.size,
    };
    let manual: Manual;
    try {
      manual = await apiFetch<Manual>("/admin/manuals", { method: "POST", body: JSON.stringify(payload) });
    } catch (caught) {
      const pendingManual = manuals.value.find(
        (item) => item.original_filename === file.name && ["DRAFT", "FAILED"].includes(item.status),
      );
      if (!pendingManual) throw caught;
      manual = pendingManual;
      notice.value = "이전에 생성된 업로드 초안을 찾아 파일 전송을 다시 시도합니다.";
    }
    const upload = await apiFetch<{ upload_url: string; required_headers: Record<string, string> }>(
      `/admin/manuals/${manual.id}/upload-url`,
      { method: "POST" },
    );
    const uploaded = await fetch(upload.upload_url, { method: "PUT", headers: upload.required_headers, body: file });
    if (!uploaded.ok) throw new Error("파일 저장소로 PDF를 전송하지 못했습니다.");
    const complete = await apiFetch<{ pdf_page_count: number }>(`/admin/manuals/${manual.id}/upload-complete`, { method: "POST" });
    notice.value = `${file.name} 업로드를 확인했습니다. ${complete.pdf_page_count}쪽 PDF가 적재 대기 상태입니다.`;
    manualForm.value = { title: "", manual_type: "OWNER_MANUAL", locale: "ko-KR", catalog_ids: [] };
    makePrimary.value = true;
    selectedFile.value = null;
    if (fileInput.value) fileInput.value.value = "";
    await loadData();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "매뉴얼을 업로드하지 못했습니다.";
    await loadData().catch(() => undefined);
  } finally {
    uploading.value = false;
  }
}

function beginManualEdit(manual: Manual): void {
  editingManualId.value = manual.id;
  manualEdit.value = {
    title: manual.title,
    manual_type: manual.manual_type,
    locale: manual.locale,
    catalog_ids: [...manual.catalog_ids],
  };
  editManualPrimary.value = manual.primary_catalog_ids.length > 0;
}

async function saveManualEdit(): Promise<void> {
  if (!editingManualId.value || !manualEdit.value.catalog_ids.length) {
    error.value = "매뉴얼을 적용할 차량을 하나 이상 선택해 주세요.";
    return;
  }
  error.value = "";
  savingEdit.value = true;
  try {
    const updated = await apiFetch<Manual>(`/admin/manuals/${editingManualId.value}`, {
      method: "PATCH",
      body: JSON.stringify({
        ...manualEdit.value,
        primary_catalog_ids: editManualPrimary.value ? manualEdit.value.catalog_ids : [],
      }),
    });
    manuals.value = manuals.value.map((manual) => (manual.id === updated.id ? updated : manual));
    editingManualId.value = null;
    notice.value = `${updated.title} 매뉴얼 정보를 수정했습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "매뉴얼을 수정하지 못했습니다.";
  } finally {
    savingEdit.value = false;
  }
}

async function deleteManual(manual: Manual): Promise<void> {
  if (!window.confirm(`${manual.title} 매뉴얼을 삭제할까요?`)) return;
  error.value = "";
  try {
    await apiFetch<void>(`/admin/manuals/${manual.id}`, { method: "DELETE" });
    manuals.value = manuals.value.filter((item) => item.id !== manual.id);
    notice.value = `${manual.title} 매뉴얼을 삭제했습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "매뉴얼을 삭제하지 못했습니다.";
  }
}

async function prepareRagTest(manual: Manual): Promise<void> {
  error.value = "";
  notice.value = "";
  preparingManualId.value = manual.id;
  try {
    const result = await apiFetch<{ indexed_page_count: number }>(`/admin/manuals/${manual.id}/prepare-rag-test`, { method: "POST" });
    notice.value = `${manual.title}의 ${result.indexed_page_count}쪽을 준비했습니다. 임베딩은 서버에서 계속 생성됩니다.`;
    await loadData();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "문서 테스트 준비를 완료하지 못했습니다.";
    await loadData().catch(() => undefined);
  } finally {
    preparingManualId.value = null;
  }
}

async function rebuildRagIndex(manual: Manual): Promise<void> {
  error.value = "";
  notice.value = "";
  preparingManualId.value = manual.id;
  try {
    const result = await apiFetch<{ indexed_page_count: number }>(`/admin/manuals/${manual.id}/rebuild-rag-index`, { method: "POST" });
    notice.value = `${manual.title}의 ${result.indexed_page_count}쪽을 다시 준비했습니다. 임베딩은 서버에서 계속 생성됩니다.`;
    await loadData();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "임베딩 재생성에 실패했습니다.";
    await loadData().catch(() => undefined);
  } finally {
    preparingManualId.value = null;
  }
}

async function updateOfficialManualUrl(catalog: Catalog): Promise<void> {
  const value = window.prompt(
    "현대 공식 웹 매뉴얼의 차량 시작 URL을 붙여 넣으세요. 저장 후 '공식 안내 갱신'을 누르면 해당 차량에 허용된 공식 웹 매뉴얼의 하위 절차를 수집합니다.",
    catalog.official_manual_url || "",
  );
  if (value === null) return;
  error.value = "";
  notice.value = "";
  try {
    const updated = await apiFetch<Catalog>(`/admin/vehicle-catalog/${catalog.id}/official-manual-url`, {
      method: "PATCH",
      body: JSON.stringify({ official_manual_url: value.trim() || null }),
    });
    catalogs.value = catalogs.value.map((item) => (item.id === updated.id ? updated : item));
    notice.value = value.trim() ? `${catalog.display_name}의 현대 공식 웹 매뉴얼 링크를 저장했습니다.` : "공식 웹 매뉴얼 링크를 지웠습니다.";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "공식 웹 매뉴얼 링크를 저장하지 못했습니다.";
  }
}

async function syncOfficialSources(catalog: Catalog): Promise<void> {
  error.value = "";
  notice.value = "";
  syncingOfficialCatalogId.value = catalog.id;
  try {
    const result = await apiFetch<{ synced_count: number }>(
      `/admin/vehicle-catalog/${catalog.id}/official-sources/sync`,
      { method: "POST" },
    );
    officialSourceCounts.value = { ...officialSourceCounts.value, [catalog.id]: result.synced_count };
    notice.value = `${catalog.display_name}의 공식 보조 안내를 갱신했습니다. ${result.synced_count}건을 준비했습니다.`;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "공식 보조 안내를 갱신하지 못했습니다.";
  } finally {
    syncingOfficialCatalogId.value = null;
  }
}

function canEditManual(manual: Manual): boolean {
  return ["DRAFT", "UPLOADED", "FAILED"].includes(manual.status);
}

async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
  clearAccessToken();
  await router.replace("/login");
}

function formatSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<template>
  <div class="admin-page">
    <header class="admin-header">
      <RouterLink class="wordmark" to="/admin">CarMe</RouterLink>
      <nav aria-label="관리자 메뉴"><a class="active" href="#vehicles">차량 카탈로그</a><a href="#manuals">매뉴얼 업로드</a><RouterLink to="/app">사용자 화면 테스트</RouterLink></nav>
      <div class="account-menu"><span>{{ accountLabel }}</span><button type="button" @click="logout">로그아웃</button></div>
    </header>
    <main class="admin-main">
      <div class="page-heading"><div><p class="kicker">ADMIN CONSOLE</p><h1>차량 매뉴얼 운영</h1><p>차량별 적용 매뉴얼을 등록하고, 검증된 PDF만 적재 흐름으로 보냅니다.</p></div><span class="role-badge">관리자</span></div>
      <p v-if="notice" class="notice success" role="status">{{ notice }}</p><p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <section id="vehicles" class="work-section" aria-labelledby="vehicles-title">
        <div class="section-heading"><div><p class="section-label">01 · 차량 카탈로그</p><h2 id="vehicles-title">차량과 연식 등록</h2></div><span>{{ catalogs.length }}개 차량</span></div>
        <form class="catalog-form" @submit.prevent="createCatalog"><VehicleCatalogFields mode="entry" v-model:manufacturer="catalogForm.manufacturer" v-model:model-name="catalogForm.model_name" v-model:model-year="catalogForm.model_year" /><button class="button primary" :disabled="savingCatalog" type="submit">{{ savingCatalog ? "등록 중" : "차량 초안 추가" }}</button></form>
        <div class="catalog-list"><div v-if="loading" class="empty-state">등록된 차량을 불러오는 중입니다.</div><div v-else-if="!catalogs.length" class="empty-state">먼저 차량과 연식을 등록해 주세요.</div><article v-for="catalog in catalogs" :key="catalog.id" class="catalog-row"><div v-if="editingCatalogId === catalog.id" class="inline-editor"><label class="field"><span>제조사</span><input v-model="catalogEdit.manufacturer" /></label><label class="field"><span>차종</span><input v-model="catalogEdit.model_name" /></label><label class="field"><span>연식</span><input v-model.number="catalogEdit.model_year" min="1980" max="2100" type="number" /></label></div><div v-else><strong>{{ catalog.display_name }}</strong><span>{{ catalog.manufacturer }} · {{ catalog.model_year }}년형{{ catalog.official_manual_url ? " · 공식 웹 매뉴얼 링크 등록됨" : "" }}</span></div><div class="catalog-meta"><span class="status-tag" :class="catalog.status.toLowerCase()">{{ catalog.status }}</span><span>준비된 매뉴얼 {{ catalog.ready_manual_count }}</span><template v-if="catalog.official_manual_url"><span>공식 보조 안내 {{ officialSourceCounts[catalog.id] ?? 0 }}건</span><a class="test-button" :href="catalog.official_manual_url" target="_blank" rel="noreferrer">공식 페이지 열기</a><button class="test-button" :disabled="syncingOfficialCatalogId === catalog.id" type="button" @click="syncOfficialSources(catalog)">{{ syncingOfficialCatalogId === catalog.id ? "갱신 중" : "공식 안내 갱신" }}</button></template><button class="test-button" type="button" @click="updateOfficialManualUrl(catalog)">공식 링크 {{ catalog.official_manual_url ? "수정" : "등록" }}</button><div v-if="catalog.status === 'DRAFT'" class="row-actions"><template v-if="editingCatalogId === catalog.id"><button type="button" @click="saveCatalogEdit">저장</button><button type="button" @click="editingCatalogId = null">취소</button></template><template v-else><button type="button" @click="beginCatalogEdit(catalog)">수정</button><button class="danger" type="button" @click="deleteCatalog(catalog)">삭제</button></template></div></div></article></div>
      </section>
      <section id="manuals" class="work-section" aria-labelledby="manuals-title">
        <div class="section-heading"><div><p class="section-label">02 · 공식 매뉴얼</p><h2 id="manuals-title">PDF 매뉴얼 업로드</h2></div><span>PDF만 가능 · 최대 200 MB</span></div>
        <form class="manual-form" @submit.prevent="uploadManual"><div class="manual-fields"><label class="field"><span>매뉴얼 제목</span><input v-model="manualForm.title" placeholder="예: 아반떼 2025 취급설명서" required /></label><label class="field"><span>종류</span><select v-model="manualForm.manual_type"><option value="OWNER_MANUAL">취급설명서</option><option value="QUICK_GUIDE">간편 안내서</option></select></label><label class="field"><span>언어</span><select v-model="manualForm.locale"><option value="ko-KR">한국어</option><option value="en-US">English</option></select></label></div><fieldset class="vehicle-selector"><legend>적용 차량</legend><p>이 매뉴얼을 적용할 차량을 선택하세요.</p><div class="checkbox-grid"><label v-for="catalog in catalogs" :key="catalog.id"><input v-model="manualForm.catalog_ids" :value="catalog.id" type="checkbox" /><span>{{ catalog.display_name }}</span></label></div><label class="primary-choice"><input v-model="makePrimary" type="checkbox" /><span>선택한 차량의 대표 매뉴얼로 지정</span></label><p class="edit-help">대표 매뉴얼은 차량 공개에 필요합니다. RAG는 이 차량에 연결된 모든 READY 매뉴얼을 검색합니다.</p></fieldset><label class="file-drop" :class="{ chosen: selectedFile }"><input ref="fileInput" accept="application/pdf,.pdf" type="file" @change="setFile" /><span class="file-title">{{ selectedFile ? selectedFile.name : "PDF 파일을 선택하세요" }}</span><small>{{ selectedFile ? formatSize(selectedFile.size) : "PDF · 최대 200 MB" }}</small></label><div class="upload-footer"><p v-if="selectedCatalogs.length">적용 대상: {{ selectedCatalogs.map((catalog) => catalog.display_name).join(", ") }}</p><p v-else>차량을 선택하면 매뉴얼 연결 대상이 표시됩니다.</p><button class="button primary" :disabled="uploading || !catalogs.length" type="submit">{{ uploading ? "파일 검증 중" : "매뉴얼 업로드" }}</button></div></form>
        <div class="manual-history"><div v-if="!manuals.length" class="empty-state">아직 업로드한 매뉴얼이 없습니다.</div><article v-for="manual in manuals" :key="manual.id" class="manual-row"><div v-if="editingManualId === manual.id" class="manual-editor"><div class="manual-fields"><label class="field"><span>매뉴얼 제목</span><input v-model="manualEdit.title" /></label><label class="field"><span>종류</span><select v-model="manualEdit.manual_type"><option value="OWNER_MANUAL">취급설명서</option><option value="QUICK_GUIDE">간편 안내서</option></select></label><label class="field"><span>언어</span><select v-model="manualEdit.locale"><option value="ko-KR">한국어</option><option value="en-US">English</option></select></label></div><div class="checkbox-grid edit-catalogs"><label v-for="catalog in catalogs" :key="catalog.id"><input v-model="manualEdit.catalog_ids" :value="catalog.id" type="checkbox" /><span>{{ catalog.display_name }}</span></label></div><label class="primary-choice"><input v-model="editManualPrimary" type="checkbox" /><span>선택한 차량의 대표 매뉴얼로 지정</span></label><p class="edit-help">대표 매뉴얼은 차량 공개에 필요합니다. RAG는 연결된 모든 READY 매뉴얼을 검색합니다. PDF 파일 자체를 바꾸려면 새 개정본으로 업로드해 주세요.</p></div><div v-else><strong>{{ manual.title }}</strong><span>{{ manual.applicable_catalogs.join(", ") }} · {{ manual.original_filename }}</span></div><div class="catalog-meta"><span class="status-tag" :class="manual.status.toLowerCase()">{{ manual.status }}</span><span v-if="manual.status === 'INDEXING'">임베딩 {{ manual.embedded_chunk_count }} / {{ manual.indexing_total_chunks }}</span><span v-else>{{ manual.pdf_page_count ? `${manual.pdf_page_count}쪽` : formatSize(manual.file_size_bytes) }}</span><div v-if="canEditManual(manual)" class="row-actions"><template v-if="editingManualId === manual.id"><button type="button" @click="saveManualEdit">저장</button><button type="button" @click="editingManualId = null">취소</button></template><template v-else><button type="button" @click="beginManualEdit(manual)">수정</button><button class="danger" type="button" @click="deleteManual(manual)">삭제</button></template></div><button v-if="manual.status === 'UPLOADED'" class="test-button" :disabled="preparingManualId === manual.id" type="button" @click="prepareRagTest(manual)">{{ preparingManualId === manual.id ? "문서 준비 중" : "RAG 테스트 준비" }}</button><button v-if="manual.status === 'READY'" class="test-button" :disabled="preparingManualId === manual.id" type="button" @click="rebuildRagIndex(manual)">{{ preparingManualId === manual.id ? "임베딩 생성 중" : "임베딩 재생성" }}</button><button v-if="!canEditManual(manual) && manual.status !== 'INDEXING'" class="text-delete" type="button" @click="deleteManual(manual)">삭제</button></div></article></div>
      </section>
    </main>
  </div>
</template>
