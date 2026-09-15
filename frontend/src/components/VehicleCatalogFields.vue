<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  mode: "entry" | "filter";
  manufacturer: string;
  modelName: string;
  modelYear: number | "";
  manufacturers?: string[];
  modelNames?: string[];
  modelYears?: number[];
  disabled?: boolean;
}>(), {
  manufacturers: () => [],
  modelNames: () => [],
  modelYears: () => [],
  disabled: false,
});

const emit = defineEmits<{
  "update:manufacturer": [value: string];
  "update:modelName": [value: string];
  "update:modelYear": [value: number | ""];
}>();

const manufacturerModel = computed({ get: () => props.manufacturer, set: (value: string) => emit("update:manufacturer", value) });
const modelNameModel = computed({ get: () => props.modelName, set: (value: string) => emit("update:modelName", value) });
const modelYearModel = computed({ get: () => props.modelYear, set: (value: number | "") => emit("update:modelYear", value) });
</script>

<template>
  <div class="vehicle-catalog-fields">
    <label class="field"><span>제조사</span><input v-if="mode === 'entry'" v-model="manufacturerModel" :disabled="disabled" required /><select v-else v-model="manufacturerModel" :disabled="disabled"><option value="">제조사를 선택해 주세요</option><option v-for="item in manufacturers" :key="item" :value="item">{{ item }}</option></select></label>
    <label class="field"><span>차종</span><input v-if="mode === 'entry'" v-model="modelNameModel" :disabled="disabled" placeholder="예: 아반떼" required /><select v-else v-model="modelNameModel" :disabled="disabled || !manufacturer"><option value="">차종을 선택해 주세요</option><option v-for="item in modelNames" :key="item" :value="item">{{ item }}</option></select></label>
    <label class="field"><span>연식</span><input v-if="mode === 'entry'" v-model.number="modelYearModel" :disabled="disabled" min="1980" max="2100" required type="number" /><select v-else v-model="modelYearModel" :disabled="disabled || !modelName"><option value="">연식을 선택해 주세요</option><option v-for="item in modelYears" :key="item" :value="item">{{ item }}년형</option></select></label>
  </div>
</template>
