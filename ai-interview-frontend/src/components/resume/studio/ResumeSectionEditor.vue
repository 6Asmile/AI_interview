<script setup lang="ts">
import { computed } from 'vue';
import draggable from 'vuedraggable';
import { Delete, Hide, Plus, Rank, View } from '@element-plus/icons-vue';

export interface ResumeSectionField {
  key: string;
  label: string;
  type?: 'text' | 'textarea' | 'date' | 'url' | 'list';
  placeholder?: string;
  span?: 1 | 2;
}

const props = defineProps<{
  title: string;
  sectionKey: string;
  items: Array<Record<string, any>>;
  fields: ResumeSectionField[];
  hidden: boolean;
}>();

const emit = defineEmits<{
  'update:items': [items: Array<Record<string, any>>];
  'toggle-hidden': [];
  add: [];
}>();

const orderedItems = computed({
  get: () => props.items,
  set: value => emit('update:items', value),
});

const stableId = (item: Record<string, any>) => item?.['x-ifaceoff']?.id || JSON.stringify(item);

function updateField(index: number, field: string, value: unknown) {
  const next = props.items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item);
  emit('update:items', next);
}

function removeItem(index: number) {
  emit('update:items', props.items.filter((_, itemIndex) => itemIndex !== index));
}

function updateList(index: number, field: string, list: string[]) {
  updateField(index, field, list);
}

function addListValue(index: number, field: string) {
  const values = [...(props.items[index]?.[field] || []), ''];
  updateList(index, field, values);
}
</script>

<template>
  <section class="section-editor" :class="{ 'section-editor--hidden': hidden }">
    <header class="section-editor__header">
      <div class="section-editor__identity">
        <el-icon class="section-editor__drag"><Rank /></el-icon>
        <div>
          <h3>{{ title }}</h3>
          <p>{{ items.length ? `${items.length} 条内容` : '尚未添加内容' }}</p>
        </div>
      </div>
      <div class="section-editor__actions">
        <el-button text :icon="hidden ? View : Hide" @click="emit('toggle-hidden')">
          {{ hidden ? '显示栏目' : '隐藏栏目' }}
        </el-button>
        <el-button type="primary" plain :icon="Plus" @click="emit('add')">添加</el-button>
      </div>
    </header>

    <el-alert
      v-if="hidden"
      title="该栏目保留在草稿中，但不会进入预览或导出。"
      type="info"
      :closable="false"
      show-icon
    />

    <draggable
      v-model="orderedItems"
      class="section-editor__items"
      :item-key="stableId"
      handle=".item-drag"
      :animation="180"
      ghost-class="drag-ghost"
    >
      <template #item="{ element: item, index }">
        <article class="resume-item">
          <header class="resume-item__header">
            <button class="item-drag" type="button" :aria-label="`拖动排序第 ${index + 1} 条内容`">
              <el-icon><Rank /></el-icon>
            </button>
            <strong>{{ item.name || item.title || item.institution || item.organization || item.language || `第 ${index + 1} 条` }}</strong>
            <el-button text type="danger" :icon="Delete" aria-label="删除条目" @click="removeItem(index)" />
          </header>
          <div class="resume-item__grid">
            <template v-for="field in fields" :key="field.key">
              <div v-if="field.type !== 'list'" class="field" :class="{ 'field--wide': field.span === 2 || field.type === 'textarea' }">
                <label :for="`${sectionKey}-${stableId(item)}-${field.key}`">{{ field.label }}</label>
                <el-input
                  :id="`${sectionKey}-${stableId(item)}-${field.key}`"
                  :model-value="item[field.key]"
                  :type="field.type === 'textarea' ? 'textarea' : 'text'"
                  :rows="field.type === 'textarea' ? 3 : undefined"
                  :placeholder="field.placeholder"
                  @update:model-value="value => updateField(index, field.key, value)"
                />
              </div>
              <div v-else class="field field--wide bullet-editor">
                <div class="bullet-editor__heading">
                  <label>{{ field.label }}</label>
                  <el-button text type="primary" :icon="Plus" @click="addListValue(index, field.key)">添加一条</el-button>
                </div>
                <draggable
                  :model-value="item[field.key] || []"
                  :item-key="(value: string) => value"
                  handle=".bullet-drag"
                  :animation="160"
                  @update:model-value="value => updateList(index, field.key, value)"
                >
                  <template #item="{ element: bullet, index: bulletIndex }">
                    <div class="bullet-row">
                      <button class="bullet-drag" type="button" aria-label="拖动成果排序"><el-icon><Rank /></el-icon></button>
                      <el-input
                        :model-value="bullet"
                        :placeholder="field.placeholder || '用行动 + 范围 + 结果描述这条成果'"
                        @update:model-value="value => {
                          const next = [...(item[field.key] || [])];
                          next[bulletIndex] = value;
                          updateList(index, field.key, next);
                        }"
                      />
                      <el-button
                        text
                        type="danger"
                        :icon="Delete"
                        aria-label="删除成果"
                        @click="updateList(index, field.key, (item[field.key] || []).filter((_: unknown, i: number) => i !== bulletIndex))"
                      />
                    </div>
                  </template>
                </draggable>
              </div>
            </template>
          </div>
        </article>
      </template>
    </draggable>

    <el-empty v-if="!items.length" :image-size="70" description="添加内容后会自动保存并刷新右侧权威预览">
      <el-button type="primary" plain :icon="Plus" @click="emit('add')">添加{{ title }}</el-button>
    </el-empty>
  </section>
</template>

<style scoped>
.section-editor { overflow: hidden; border: 1px solid #d7dee7; border-radius: 14px; background: #fff; }
.section-editor--hidden { background: #f7f8fa; }
.section-editor__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 18px; border-bottom: 1px solid #e7ebf0; }
.section-editor__identity, .section-editor__actions, .resume-item__header, .bullet-editor__heading, .bullet-row { display: flex; align-items: center; }
.section-editor__identity { gap: 12px; }
.section-editor__identity h3 { margin: 0 0 3px; color: #18212f; font-size: 17px; }
.section-editor__identity p { margin: 0; color: #667085; font-size: 12px; }
.section-editor__actions { gap: 6px; }
.section-editor__drag, .item-drag, .bullet-drag { color: #667085; cursor: grab; }
.section-editor__drag { font-size: 18px; }
.section-editor :deep(.el-alert) { margin: 14px 16px 0; }
.section-editor__items { display: grid; gap: 12px; padding: 14px; }
.resume-item { border: 1px solid #e0e5eb; border-radius: 12px; background: #fbfcfd; }
.resume-item__header { gap: 10px; padding: 10px 12px; border-bottom: 1px solid #e7ebf0; }
.resume-item__header strong { flex: 1; min-width: 0; overflow: hidden; color: #2b3545; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.item-drag, .bullet-drag { display: inline-grid; padding: 4px; border: 0; background: transparent; place-items: center; }
.resume-item__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 14px; }
.field { min-width: 0; }
.field--wide { grid-column: 1 / -1; }
.field > label, .bullet-editor__heading label { display: block; margin-bottom: 6px; color: #445064; font-size: 12px; font-weight: 650; }
.bullet-editor__heading { justify-content: space-between; }
.bullet-row { gap: 8px; margin-bottom: 8px; }
.bullet-row :deep(.el-input) { flex: 1; }
.drag-ghost { opacity: .42; background: #e8f0ff; }
@media (max-width: 760px) {
  .section-editor__header { align-items: flex-start; flex-direction: column; }
  .section-editor__actions { width: 100%; justify-content: space-between; }
  .resume-item__grid { grid-template-columns: 1fr; }
  .field--wide { grid-column: auto; }
}
</style>
