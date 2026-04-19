<script setup lang="ts">
defineProps<{
  cols: string
  clickable?: boolean
}>()
</script>

<template>
  <div
    class="t-row px-2"
    :class="{ 'cursor-pointer': clickable }"
    :style="{ gridTemplateColumns: cols }"
  >
    <slot />
  </div>
</template>
