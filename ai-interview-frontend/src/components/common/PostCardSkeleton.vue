<template>
  <router-link
    :to="`/dashboard/blog/${id}`"
    class="flex items-center justify-between p-5 no-underline transition-all duration-300 hover:bg-white/70"
  >
    <div class="flex flex-col justify-between flex-1 pr-4">
      <div>
        <h3
          class="text-base font-semibold text-black mb-1 hover:text-blue-600 transition line-clamp-2"
        >
          {{ title }}
        </h3>
        <p class="text-sm text-gray-700 leading-snug line-clamp-2">
          {{ excerpt }}
        </p>
      </div>

      <div class="flex items-center text-xs text-gray-500 mt-3 space-x-2">
        <span>{{ author || "佚名" }}</span>
        <span>·</span>
        <span>{{ date }}</span>
      </div>
    </div>

    <div
      v-if="cover && cover !== 'null'"
      class="w-32 h-20 flex-shrink-0 rounded-xl bg-center bg-cover border border-gray-200/60 shadow-sm"
      :style="{ backgroundImage: `url(${cover})` }"
    ></div>
    <div
      v-else
      class="w-32 h-20 flex-shrink-0 rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center text-gray-500 text-xs border border-gray-200/60"
    >
      无封面
    </div>
  </router-link>
</template>

<script lang="ts" setup>
defineProps<{
  id: number | string;
  title: string;
  excerpt?: string;
  cover?: string | null;
  author?: string;
  date?: string;
}>();
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
</style>
